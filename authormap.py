#!/usr/bin/env python3

import argparse
import pwd
import subprocess
from xml.etree import ElementTree


def xml_log(url):
    return subprocess.check_output(('svn', 'log', '--xml', url))


def iter_authors(xml):
    root = ElementTree.fromstring(xml)
    for author in root.iter('author'):
        yield author.text


def lookup_author(author):
    if author.endswith('-guest'):
        dd_name = author.rsplit('-', 1)[0]
        try:
            pwd.getpwnam(dd_name)
        except KeyError:
            pass
        else:
            return lookup_author(dd_name)

    name = None
    try:
        user = pwd.getpwnam(author)
        name = user.pw_gecos
    except KeyError:
        return '', ''
    if not author.endswith('-guest'):
        return name, author + '@debian.org'
    return name, ''


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--svn-repo', help='URL to the SVN repo')
    p.add_argument('--author-list', type=open,
                   help='List of usernames, one per line')
    p.add_argument('--write-author-list', type=argparse.FileType('w'),
                   help='Write a list of usernames, one per line')
    p.add_argument('--write-identity-map', type=argparse.FileType('w'),
                   help='Write an identity map')
    args = p.parse_args()

    if args.svn_repo:
        xml = xml_log(args.svn_repo)
        authors = dict.fromkeys(iter_authors(xml))
    elif args.author_list:
        authors = {}
        with args.author_list as f:
            for line in f:
                authors[line.strip()] = None
    else:
        raise p.error('--svn-repo or --author-list is required')

    if args.write_author_list:
        with args.write_author_list as f:
            f.write('\n'.join(authors))
            f.write('\n')

    if args.write_identity_map:
        for author in authors.keys():
            authors[author] = lookup_author(author)

        with args.write_identity_map as f:
            for author, (name, email) in sorted(authors.items()):
                f.write('{} = {} <{}>\n'.format(author, name, email))

if __name__ == '__main__':
    main()
