#!/usr/bin/env python3

import argparse
import os
import shutil
import subprocess
import re


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
    write_rules()
    migrate(args.svn_repo, args.target_dir, identity_map=args.identity_map,
            svn2git=args.svn2git)


def prepare(target):
    if os.path.exists(target):
        shutil.rmtree(target)
    os.mkdir(target)


def write_rules():
    packages = []
    with open('packages') as f:
        for line in f:
            packages.append(line.strip())

    with open('rules.txt', 'w') as f:
        for package in packages:
            f.write('create repository {}\n'.format(package))
            f.write('end repository\n\n')
        f.write(r'''
match /(metainfo|modules|tools|www)/
end match

match /packages/(trunk|tags|debian)/
end match

# packages that get renamed
match /packages/(pyth|python-pyth)/
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
    rules = os.path.abspath('rules.txt')
    target = os.path.abspath(target)
    cmd = [svn2git, '--rules', rules, '--stats']
    if identity_map:
        cmd += ['--identity-map', identity_map]
    cmd.append(svn_repo)
    subprocess.check_call(cmd, cwd=target)


def clean_svn_buildpackages_commits(gitdir):
    """Rewrites svn-buildpackages so that the only have one parent."""

    run = subprocess.check_output

    base_git_args = ['git', '--git-dir={}'.format(gitdir)]
    refs = run(base_git_args + ['show-ref', '--tags'])

    is_svn_buildpackage = re.compile(b'\n\n\[svn-buildpackage\]',
                                     flags=re.DOTALL).search

    for ref in refs.splitlines():
        ref_sha, _, ref_name = ref.partition(b' ')
        commit = run(base_git_args + ['cat-file', '-p', ref_sha])
        if is_svn_buildpackage(commit):
            first_parent = run(
                base_git_args + ['rev-list', ref_sha, '-n 2']
            ).splitlines()[1]
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
