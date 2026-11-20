.PHONY: ci hooks

ci:
	bash scripts/ci.sh

# Same relay as repo-init.sh: the hooks dir is shared by worktrees, so the relay runs the pushing checkout's .githooks/pre-push.
hooks:
	@push="$$(git rev-parse --git-path hooks)/pre-push"; mark="# >>> versioned pre-push relay >>>"; \
	if [ -f "$$push" ] && grep -qF "$$mark" "$$push"; then echo "pre-push: already present"; \
	elif [ -e "$$push" ] || [ -L "$$push" ]; then echo "pre-push: NOT installed, $$push already exists (merge it by hand)"; exit 1; \
	else printf '%s\n' '#!/bin/sh' "$$mark" \
	  'h="$$(git rev-parse --show-toplevel)/.githooks/pre-push"' \
	  '[ -f "$$h" ] || exit 0' \
	  '[ -x "$$h" ] && exec "$$h" "$$@"' \
	  'exec sh "$$h" "$$@"' > "$$push" && chmod +x "$$push" && echo "pre-push: installed ($$push)"; fi
