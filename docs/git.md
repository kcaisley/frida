# Git Commit Message Format

Follow these rules on each commit:

1. Don't add attributions in the commit messages, it really makes the commit history messy.
2. First line: 80 characters or less, summarize the general work done without making massive assumptions about purpose
3. Subsequent lines: Format with `- ` prefix, one entry per type of change made
4. Multiple files, one change type: Counts as one entry
5. One file, multiple change types: Create separate entries if changes are significant
6. Always push: After creating a commit, immediately push to origin with `git push`
