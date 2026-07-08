set -e

git stash

git checkout main
git pull

.venv/bin/jupyter-book clean -a docs
.venv/bin/jupyter-book build docs

cp docs/_images/* docs/_build/html/_images
.venv/bin/python deq/site.py

SITE_DIR=/var/www/html/on-draft
rm -rf $SITE_DIR/*
cp -r docs/_build/html/* $SITE_DIR

echo "site deployed to $SITE_DIR"
echo "Note: any pre-publish stash is still saved. Run 'git stash pop' to restore."
