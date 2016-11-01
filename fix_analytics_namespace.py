#!/usr/bin/env python
import argparse
from glob import glob
import logging
import os
import re
import shutil
from subprocess import check_output, check_call, call, PIPE
import sys

description = """ This was created to take the analytics-python package
which segment.io provides and rename it to segmentio to avoid namespace
conflicts.

Works this way:

  1) based on a `segment-release` branch 
  2) update the master based on segmentio/analytics-python
  3) confirm an new release needs to happen
  4) merge the new release into `segment-release`
  5) generate 'segmentio' package from 'analytics' & update 'setup.py'
  6) commit new 'segmentio' changes

"""

logging.basicConfig(
    format='%(levelname)s (L%(lineno)s): %(message)s', 
    stream=sys.stdout, 
    level=logging.DEBUG,
)


def get_segmentio_analytics_python_remote():
    remotes = check_output(["git", "remote", "-v"])
    pattern = (
        '(?P<name>[a-zA-Z_]*)'
        '\t(?P<url>git@github\.com:segmentio/analytics-python)'
        ' \(fetch\)'
    )
    m = re.search(pattern, remotes)
    if m is None:
        raise ValueError('could not find segment remote')
    name, url = m.groups()
    return name, url


def fetch_master_from_segmentio_analytics_python():
    name, url = get_segmentio_analytics_python_remote()
    check_call(['git', 'fetch', name, 'master'])
    check_call(['git', 'fetch', '--tags', name])


def checkout_segmentio_branded_branch():
    fixed_branch = 'segmentio-release'
    current_branch = check_output(['git', 'rev-parse', '--abbrev-ref', 'HEAD'])

    if fixed_branch != current_branch:
        exists = call(['git', 'rev-parse', '--verify', fixed_branch])
        if exists != 0:
            tag = check_output(['git', 'describe', 'master']).rstrip()
            raise StandardError(
                "\n\nwhy don't you have branch {0}?!"
                "\n run `git checkout -b {0} tags/{1}` to create"
                "\n then make sure you have this file committed"
                .format(fixed_branch, tag)
            )
        check_call(['git', 'checkout', fixed_branch])
 

def get_most_recent_tag():
    most_recent_tag = check_output(['git', 'describe', 'master']).rstrip()

    cmd = ['git', 'describe', '--abbrev=0', '--tags']
    current_tag = check_output(cmd).rstrip()

    logging.debug('current_local_tag: {}'.format(current_tag))
    logging.debug('most_recent_tag: {}'.format(most_recent_tag))
    
    if current_tag == most_recent_tag:
        logging.info('version up-to-date with analytics-python Release')

    return current_tag, most_recent_tag


def merge_tagged_version(tag):
    most_recent_tag_branch = 'tags/{}'.format(tag)
    check_call([
        'git', 'merge', '--no-commit', 
        '-X', 'theirs', most_recent_tag_branch,
    ])
    msg = "merged Release {}".format(tag)
    check_call(['git', 'commit', '-am', msg])


def create_segmentio_branded_package(rel_path=None):
    if rel_path is None:
        rel_path = ['']

    p = ['analytics'] + rel_path + ['*']
    search = os.path.join(*p)
    filelist = glob(search)
    for filepath in filelist:

        filename = os.path.basename(filepath)
        p = ['segmentio'] + rel_path + [filename]
        filepath_out = os.path.join(*p)

        if os.path.isdir(filepath):
            os.mkdir(filepath_out)
            create_segmentio_branded_package(rel_path + [filename])

        elif filepath.endswith('.py'):        
            with open(filepath) as f:
                c = f.read()            
                c = c.replace('import analytics', 'import segmentio')
                c = c.replace('from analytics.', 'from segmentio.')

            with open(filepath_out, 'w') as f:
                f.write(c)

            cmd = ['diff', '-q', filepath, filepath_out]
            differ = call(cmd, stdout=PIPE, stderr=PIPE)

            if differ:
                msg = (
                    '{:>12} file `diff {} {}`'
                    .format('refactored', filepath, filepath_out)
                )
            else:
                msg = (
                    '{:>12} file  src:{} dest:{}`'
                    .format('copied', filepath, filepath_out)
                )
            logging.debug(msg)

        else:
            msg = (
                '{:>12} file  src:{} dest:{}`'
                .format('copied', filepath, filepath_out)
            )
            logging.debug(msg)            
            shutil.copyfile(filepath, filepath_out)


def refactor_setup_with_segmentio_branding():    
    fn = 'setup.py'
    with open(fn) as f:
        c = f.read()

    c = c.replace(
        "name='analytics-python'", 
        "name='segmentio'",
    )
    c = c.replace(
        "test_suite='analytics.test.all'",
        "test_suite='segmentio.test.all'",
    )
    c = c.replace(
        "packages=['analytics', 'analytics.test']",
        "packages=['segmentio', 'segmentio.test']"
    )

    with open(fn, 'w') as f:
        f.write(c)

parser = argparse.ArgumentParser(
    description=description,
    formatter_class=argparse.RawTextHelpFormatter,
)  
parser.add_argument(
    '--skip-release-merge',    
    action='store_true',
)

if __name__ == '__main__':

    pargs = parser.parse_args()

    cmd = ['git', 'rev-parse', '--verify', 'HEAD']
    starting_commit = check_output(cmd).rstrip()
    logging.info(
        '\nif anything goes wrong revert to current state with:'
        '\n `git reset --hard {}`'
        .format(starting_commit)
    )

    logging.info('fetching from segmentio/analytics-python')
    fetch_master_from_segmentio_analytics_python()

    logging.info('checkout segmentio branded branch')
    checkout_segmentio_branded_branch()

    logging.info('extracting most recent tag tags')
    current_tag, most_recent_tag = get_most_recent_tag()

    if not pargs.skip_release_merge:
        if current_tag == most_recent_tag:
            sys.exit(0)

        logging.info('merge most recent tagged version')
        merge_tagged_version(most_recent_tag)

    try:
        logging.info('clobber segmentio generated packaged')
        if os.path.isdir('segmentio'):
            shutil.rmtree('segmentio')            
        os.mkdir('segmentio')

        logging.info('generate segmentio package')
        create_segmentio_branded_package()
        refactor_setup_with_segmentio_branding()

        logging.info('commit segmentio package creation')
        msg = "created segmentio release"
        check_call(['git', 'add', 'segmentio'])
        check_call(['git', 'commit', '-am', msg])

    except Exception:

        logging.error('whoops, resetting to initial commit for you')
        # reset to pior to merging release
        check_call(['git', 'reset', '--hard', starting_commit])
        raise 

    logging.info('now you may run: `git push origin segmentio-release`')
    logging.info(
        'successfully created segmentio Release {}'
        .format(most_recent_tag)
    )

