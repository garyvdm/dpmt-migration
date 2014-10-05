#!/usr/bin/env python3

import argparse
import os
import shutil
import subprocess
import re
from xml.etree import ElementTree


def main():
    p = argparse.ArgumentParser()
    p.add_argument('svn_repo',
                   help='Source SVN repo')
    p.add_argument('--target-dir', default='from-svn',
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
        print('Cleaning svn-buildpackage tags in {}'.format(package))
        clean_svn_buildpackages_commits(os.path.join(args.target_dir, package))


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

    # Skip empty repositories, and ones without tags
    for type_ in ('heads', 'tags'):
        if not os.listdir(os.path.join(gitdir, 'refs', type_)):
            return

    run = subprocess.check_output

    base_git_args = ['git', '--git-dir={}'.format(gitdir)]
    refs = run(base_git_args + ['show-ref', '--tags'])

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


if __name__ == '__main__':
    main()
