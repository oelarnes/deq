.venv/bin/jupyter-book clean -a docs
.venv/bin/jupyter-book build docs

# .venv/bin/python deq/site.py
cp docs/_images/* docs/_build/html/_images

