#!/bin/bash
# Get the current branch name, handling detached HEAD cases
branch_name=$(git symbolic-ref --short -q HEAD || echo "detached")

# Only proceed with validation if we're not in a detached HEAD state
if [ "$branch_name" == "detached" ]; then
  echo "Skipping branch name check as we're in a detached HEAD state."
  exit 0
fi

# Validate the branch name against the convention
if [[ ! $branch_name =~ ^(feat|fix|docs|style|refactor|test|chore|hotfix|ci|perf|revert)(/[a-z0-9_.-]+)+$ ]]; then
  echo "Error: Branch name '$branch_name' does not follow the naming convention."
  echo "Expected format: <type>/<scope>-<description>"
  exit 1
fi
