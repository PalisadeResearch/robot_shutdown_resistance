{
  inputs = {
    nixpkgs.url = github:NixOS/nixpkgs/nixpkgs-unstable;
    flake-utils.url = github:numtide/flake-utils;
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
    with nixpkgs.legacyPackages.${system};
    let
      scripts = {
        "in" = ''echo "This alias is deprecated. Use 'run' to run evals instead."; exit 1'';
        "git-snapshot" = ''
          # git-snapshot: Create a commit from the current working copy without modifying anything
          # Usage: git-snapshot [tag-name] [commit-message]
          set -e
          NAME="''${1:-snapshot-$USER-$(date +%Y-%m-%d-%H-%M-%S)}"
          COMMIT_MSG="''${2:-Snapshot of working copy at $(date)}"
          HEAD_COMMIT=$(git rev-parse HEAD)
          export GIT_INDEX_FILE=$(mktemp)
          trap "rm -f $GIT_INDEX_FILE" EXIT
          cp .git/index "$GIT_INDEX_FILE" 2>/dev/null || true
          git add -A
          COMMIT=$(echo "$COMMIT_MSG" | git commit-tree "$(git write-tree)" -p "$HEAD_COMMIT")
          git branch "$NAME" "$COMMIT"
          echo $NAME
        '';
        "run" = ''
          set -e
          pyright .
          SNAPSHOT=$(git snapshot)
          git push origin $SNAPSHOT
          export INSPECT_GIT_ORIGIN=$(git remote get-url origin)
          export INSPECT_GIT_COMMIT=$(git rev-parse --short $SNAPSHOT)
          trap "rm -f $SNAPSHOT.log" EXIT
          # Parse parallelism from first arg (default to 1)
          PARALLEL=''${1:-1}
          shift 2>/dev/null || true
          
          PARALLEL_FLAGS=""
          if [[ "$PARALLEL" -gt 1 ]]; then
            PARALLEL_FLAGS="--max-subprocesses $PARALLEL --max-sandboxes $PARALLEL --max-connections $PARALLEL"
          fi
          
          if [[ "$(uname)" == "Darwin" ]]; then
            script -q $SNAPSHOT.log inspect eval dog_shutdown.py $PARALLEL_FLAGS "$@"
          else
            script -q -c "inspect eval dog_shutdown.py $PARALLEL_FLAGS $*" $SNAPSHOT.log
          fi
          if log=$(grep -oE 's3://[^ ]+\.eval' $SNAPSHOT.log | tail -n 1); then
            name=$(basename "$log")
            echo "Web link: https://dsa-inspect-internal.fly.dev/#/logs/$name"
            echo
            price "$log"
          else
            echo "Cost estimation failed because I failed to identify the log file."
          fi
        '';
        "publish" = ''
          'publish' is deprecated. The new workflow is to set variables in your .env that auto-publish your logs to https://dsa-inspect-internal.fly.dev
        '';
        "price" = ''python costs/compute_log_cost.py "$@"'';
        "gen" = ''
          python -c 'import conf; print(conf.obfuscated_binary_strings)' | \
            go run obfuscator.go -input - -output strings.go -source conf.py
        '';
        "next_task" = "gen && go run next_task.go strings.go";
      };
    in {
      devShell = stdenvNoCC.mkDerivation {
        name = "shell";
        buildInputs = lib.attrsets.mapAttrsToList writeShellScriptBin scripts ++ [
          awscli2
          flyctl
          git-lfs
          go
          uv
        ];
        shellHook = ''
          export PATH="$PROJECT_ROOT/scripts:$PATH"
          export DOCENT_ENV_PATH="$PROJECT_ROOT/.env"
          export INSPECT_EVAL_REASONING_SUMMARY=auto;
        '';
      };
    });
}
