#!/usr/bin/env python3

import argparse
import os
import shutil
import subprocess
import re
from pathlib import Path
from xml.etree import ElementTree
from contextlib import contextmanager
from functools import cmp_to_key

from apt.debfile import DscSrcPackage as Package
from apt_pkg import version_compare


def main():
    p = argparse.ArgumentParser()
    p.add_argument('svn_repo',
                   help='Source SVN repo')
    p.add_argument('--target-dir', default='from-svn',
                   help='Parent directory for git repos')
    p.add_argument('--debsnap-dir', default='debsnap',
                   help='Parent directory for git repos')
    p.add_argument('--svn2git', default='svn-all-fast-export',
                   help='svn-all-fast-export (svn2git) binary')
    p.add_argument('--identity-map', type=open,
                   help='identity-map of svn usernames to git authors')
    args = p.parse_args()

    prepare(args.target_dir)
    packages = list_packages(args.svn_repo)
    write_rules(packages)
    migrate(args.svn_repo,
            args.target_dir,
            identity_map=args.identity_map.name,
            svn2git=args.svn2git)
    for package in sorted(packages):
        print(package)
        gitdir = os.path.join(args.target_dir, package)
        clean_svn_buildpackages_commits(gitdir)
        rename_svn_import_refs(gitdir)
        #get_dscs(args.debsnap_dir, package)
        import_dscs(args.debsnap_dir, package, gitdir)


def prepare(target):
    """Blow away any existing target directory"""
    if os.path.exists(target):
        shutil.rmtree(target)
    os.mkdir(target)


def list_packages(svn_repo):
    """
    Traverse all the revisions in the SVN repo, listing contents of the
    packages directory.
    """
    svn_url = 'file://' + os.path.abspath(svn_repo)
    xml = subprocess.check_output(
        ('svn', 'log', '--xml', '--verbose', svn_url))
    return set(iter_packages(xml))


def iter_packages(xml):
    """Yield packages from svn log XML"""
    root = ElementTree.fromstring(xml)
    for path in root.iter('path'):
        if path.get('kind') == 'dir':
            parts = path.text.split('/', 3)
            if len(parts) > 2 and parts[1] == 'packages':
                yield parts[2]


def write_rules(packages):
    """Generate a rules file"""
    with open('rules.txt', 'w') as f:
        for package in packages:
            f.write('create repository {}\n'.format(package))
            f.write('end repository\n\n')
        f.write(r'''
match /(metainfo|modules|tools|www)/
end match

match /packages/(trunk|tags|debian)/
end match

# packages that get renamed. YOLO.
match /packages/((python-)?pyth|python-(shpinx-)?releases)/
end match

match (?:/packages)?/([^/]+)/trunk/
  repository \1
  branch master
end match

#match (?:/packages)?/([^/]+)/branches/([^/]+)/
#  repository \1
#  branch \2
#end match

match (?:/packages)?/([^/]+)/branches/
end match

match (?:/packages)?/([^/]+)/tags/([^/]+)/
  repository \1
  branch refs/tags/\2
  # same as git-buildpackage's _sanitize_version
  substitute branch s/~/_/
  substitute branch s/:/%/
end match

match (?:/packages)?/([^/]+)/debian/
  repository \1
  branch master
end match

match (?:/packages)?/([^/]+)/(?!debian|branches|tags|trunk)[^/]+
end match
''')


def migrate(svn_repo, target, identity_map, svn2git):
    """Run the svn2git migration"""
    rules = os.path.abspath('rules.txt')
    svn_repo = os.path.abspath(svn_repo)
    cmd = [svn2git, '--rules', rules, '--stats']
    if identity_map:
        cmd += ['--identity-map', identity_map]
    cmd.append(svn_repo)
    subprocess.check_call(cmd, cwd=target)


def clean_svn_buildpackages_commits(gitdir):
    """
    Rewrites svn-buildpackage tags so that they only have one parent.

    svn-buildpackage uses "svn cp . REMOTE_URL" when generating tags, so if the
    working directory is out of date, tag commits have many parents.
    """

    run = subprocess.check_output
    base_git_args = ['git', '--git-dir={}'.format(gitdir)]

    try:
        refs = run(base_git_args + ['show-ref', '--tags'])
    except subprocess.CalledProcessError:
        # Skip empty repositories, and ones without tags
        return

    is_svn_buildpackage = re.compile(b'\n\n\[svn-buildpackage\]',
                                     flags=re.DOTALL).search

    for ref in refs.splitlines():
        ref_sha, _, ref_name = ref.partition(b' ')
        commit = run(base_git_args + ['cat-file', '-p', ref_sha])
        if is_svn_buildpackage(commit):
            parents = run(
                base_git_args + ['rev-list', ref_sha, '-n 3']
            ).splitlines()
            if len(parents) < 2:
                print('Orphaned tag commit: {} {}'.format(ref_sha, ref_name))
                continue
            elif len(parents) < 3:
                # No octopuses detected
                continue
            first_parent = parents[1]

            r = b'^parent (?!' + first_parent + b').*?\n'
            new_commit, _ = re.subn(r, b'', commit, flags=re.MULTILINE)

            hash_object_proc = subprocess.Popen(
                base_git_args + ['hash-object', '-w', '-t', 'commit',
                                 '--stdin'],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE)
            hash_object_proc.stdin.write(new_commit)
            hash_object_proc.stdin.close()
            hash_object_proc.wait()
            new_commit_sha = hash_object_proc.stdout.read().strip()

            run(base_git_args + [
                'update-ref', '-m', 'svn-buildpackage multiple parent cleanup',
                ref_name, new_commit_sha, ref_sha])


def rename_svn_import_refs(gitdir):
    # Rename master created by svn import to svn so that the dsc import
    # can go into master. Also rename all tags to svn/<name>.

    os.rename(os.path.join(gitdir, 'refs', 'heads', 'master'),
              os.path.join(gitdir, 'refs', 'heads', 'svn'))

    tags_path = os.path.join(gitdir, 'refs', 'tags')
    svntags_path = os.path.join(gitdir, 'refs', 'tags', 'svn')
    tags = list(os.listdir(tags_path))
    os.mkdir(svntags_path)
    for name in tags:
        os.rename(os.path.join(tags_path, name),
                  os.path.join(svntags_path, name),)


def get_dscs(debsnap_dir, package, verbose=False):
    # First grab all the versions available via debsnap.
    package_debsnap_dir = os.path.join(debsnap_dir, package)
    cmd = ['debsnap', '--force', '-d', str(package_debsnap_dir)]
    if verbose:
        cmd.append('--verbose')
    cmd.append(package)
    subprocess.check_call(cmd)

    ## Now grab all the chdist versions if there are any requested.
    ## Because this will download to the current working directory,
    ## temporarily cd there.
    #with chdir(package_debsnap_dir):
    #    for release in args.chdists:
    #        check_call(['chdist', 'apt-get', release, 'source',
    #                    '--download-only', '-qq', package])


def import_dscs(debsnap_dir, package, gitdir):
    dsc_versions = []
    package_debsnap_dir = Path(os.path.join(debsnap_dir, package))
    # Get the downloaded .dscs, and sort by Debian version.
    # requires python-apt >= 0.9.3.10.
    for filename in package_debsnap_dir.glob('*.dsc'):
        filename = os.path.abspath(str(filename))
        package = Package(filename)
        version = package['Version']
        dsc_versions.append((version, filename))

    # Sort by Debian version number.
    def compare(a, b):
        return version_compare(a[0], b[0])
    dsc_versions.sort(key=cmp_to_key(compare))

    # A non bare repo is needed to create the pristine-tar commits.
    # We also want a master with nothing in it. Create a temp git repo.
    import_repo = '{}.import_dsc'.format(gitdir)
    subprocess.check_output(['git', 'init', import_repo])

    with chdir(import_repo):
        for version, filename in dsc_versions:
            subprocess.check_call(['git-import-dsc', str(filename),
                                   '--pristine-tar',
                                   '--author-is-committer',
                                   '--author-date-is-committer-date',
                                   '--create-missing-branches',
                                   ])

    run = subprocess.check_output
    base_git_args = ['git', '--git-dir={}'.format(gitdir)]
    run(base_git_args + ['fetch', import_repo,
                         'master:master', 'upstream:upstream'])
    shutil.rmtree(import_repo)

    try:
        refs = run(base_git_args + ['show-ref', '--tags'])
    except subprocess.CalledProcessError:
        # Skip empty repositories, and ones without tags
        return

    svn_tags = {}
    debian_tags = {}
    for ref in refs.splitlines():
        ref_sha, _, ref_name = ref.rpartition(b' ')
        suffex, _, version = ref_name.rpartition(b'/')
        version = version.decode('utf-8')
        if suffex == b'refs/tags/svn':
            svn_tags[version] = ref_sha
        if suffex == b'refs/tags/debian':
            debian_tags[version] = ref_sha
    print(svn_tags)
    rebased_refs = []
    for version, filename in dsc_versions:
        print(version)
        tag_sha = debian_tags[version]
        tag = run(base_git_args + ['cat-file', '-p', debian_tags[version]])
        commit_sha = re.match(b'^object (.*)$', tag, re.MULTILINE).group(1)
        commit = run(base_git_args + ['cat-file', '-p', commit_sha])
        for old, new in rebased_refs:
            commit = commit.replace(old, new)
        if version in svn_tags:
            before, part, after = commit.partition(b'\nauthor')
            commit = before + b'\nparent ' + svn_tags[version] + part + after
        print(commit)
        hash_object_proc = subprocess.Popen(base_git_args + [
            'hash-object', '-w', '-t', 'commit', '--stdin'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        new_commit_sha, _ = hash_object_proc.communicate(commit)
        new_commit_sha = new_commit_sha.strip()
        run(base_git_args + ['update-ref',
            'refs/tags/debian/{}'.format(version), new_commit_sha, tag_sha])
        rebased_refs.append((commit_sha, new_commit_sha))
    print (rebased_refs)

    run(base_git_args + ['update-ref', 'refs/heads/master', new_commit_sha])


@contextmanager
def chdir(path):
    here = os.getcwd()
    try:
        os.chdir(str(path))
        yield
    finally:
        os.chdir(here)

if __name__ == '__main__':
    main()

