set -e

STATE_DIR="$HOME/.local/state/deq"
LOG_DIR="$STATE_DIR/logs"
mkdir -p "$LOG_DIR"
find "$LOG_DIR" -name 'publish-*.log' -mtime +30 -delete
LOG="$LOG_DIR/publish-$(date +%F-%H%M%S).log"
ln -sfn "$LOG" "$LOG_DIR/latest.log"

exec > >(tee "$LOG") 2>&1
TEE_PID=$!

# one line per run in history.log, so a glance shows which runs failed and
# which sets site.py had to skip
record_run() {
    status=$?
    # close the pipe to tee and let it finish writing before the log is read
    exec >&- 2>&-
    wait "$TEE_PID"
    failed=$(sed -n 's/^  FAILED \([^:]*\):.*/\1/p' "$LOG" | paste -sd, -)
    if [ "$status" -ne 0 ]; then
        result="FAILED (exit $status)"
    elif [ -n "$failed" ]; then
        result="partial (failed: $failed)"
    else
        result="ok"
    fi
    echo "$(date '+%F %T') $result $(basename "$LOG")" >> "$STATE_DIR/history.log"
}
trap record_run EXIT

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
