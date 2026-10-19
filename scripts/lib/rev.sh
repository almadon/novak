# The git revision that last changed some paths of the checkout.
#
# Services whose code is bind-mounted from the checkout (ingest, gateway,
# persona, the router hook) are not recreated by `docker compose up` when a pull
# changes that code: the image and the compose config are the same, so a running
# container keeps serving the old code until something restarts it. up.sh passes
# this revision to each such service as an environment variable, so a change to
# its code changes its config and compose recreates it, and only it.
#
#   code_rev gateway/novak_gateway gateway/Dockerfile   -> a short hash, or empty
code_rev() {
  git -C "$REPO_DIR" log -1 --format=%h -- "$@" 2>/dev/null || true
}
