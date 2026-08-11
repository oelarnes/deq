set -e

git stash

git checkout main
git pull

# cron's PATH is /usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin,
# which does not include where pdm lives
export PATH="$HOME/.local/bin:$PATH"

# match the venv to the lockfile just pulled, so a dependency bump cannot leave
# the code ahead of the environment. No --prod or --only-keep: jupyter-book is
# a dev dependency and this script runs it.
pdm sync

.venv/bin/jupyter-book clean -a docs
.venv/bin/jupyter-book build docs

cp docs/_images/* docs/_build/html/_images
.venv/bin/python deq/site.py

SITE_DIR=/var/www/html/on-draft
rm -rf $SITE_DIR/*
cp -r docs/_build/html/* $SITE_DIR

echo "site deployed to $SITE_DIR"
echo "Note: any pre-publish stash is still saved. Run 'git stash pop' to restore."
