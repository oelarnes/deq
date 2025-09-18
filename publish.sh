jupyter-book clean -a docs
jupyter-book build docs

.venv/bin/python deq/site.py

SITE_DIR=/var/www/html/on-draft 
rm -rf $SITE_DIR/*
cp -r docs/_build/html/* $SITE_DIR

echo "site deployed to $SITE_DIR"
