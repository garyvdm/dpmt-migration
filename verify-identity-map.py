#!/usr/bin/env python3

import argparse
import collections
import re


def main():
    p = argparse.ArgumentParser()
    p.add_argument('identity_map', type=open,
                   help='identity-map file')
    args = p.parse_args()
    verify_map(args.identity_map)


def verify_map(identity_map):
    by_name = collections.defaultdict(set)
    by_email = collections.defaultdict(set)

    with open('identity-map') as f:
        for line in f:
            m = re.match(r'^(\w+) = (.*) <(.*)>$', line.strip())
            if m:
                username, name, email = m.groups()
                by_name[name].add(email)
                by_email[email].add(name)

    for name, emails in by_name.items():
        if len(emails) > 1:
            print(name, sorted(emails))

    for email, names in by_email.items():
        if len(names) > 1:
            print(email, sorted(names))


if __name__ == '__main__':
    main()
