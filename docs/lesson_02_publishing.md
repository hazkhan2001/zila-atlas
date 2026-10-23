# Lesson 2: publishing with git and GitHub Pages

Git keeps a history of your project. GitHub stores a copy online. Pages turns
the `site/` folder of that copy into a website. You only do the setup once.

## The ideas

- **Repository (repo):** the project folder plus its full history.
- **Commit:** one saved snapshot, with a message saying what changed.
- **Branch:** a line of history. `main` is the one GitHub Pages publishes.
- **Remote:** the online copy. Its usual nickname is `origin`.
- **Push:** send your new commits to the remote.

## The commands (run them inside the `pakdata` folder)

```bash
git init -b main                 # turn this folder into a repo, first branch called main
git add .                        # stage everything (.gitignore keeps junk out)
git status                       # read what is staged before you commit
git commit -m "Zila Atlas v1"    # save the snapshot
git remote add origin https://github.com/YOUR-NAME/YOUR-REPO.git
git push -u origin main          # upload; -u remembers origin/main for next time
```

Later updates are three lines:

```bash
git add .
git commit -m "Update core inflation to October"
git push
```

## Why `git status` first

`git add .` takes everything it is allowed to. Reading `git status` before
committing is how you catch a file you did not mean to publish. Everything in
a public repo is public, including old versions of files you later delete.

## What the workflow file does

`.github/workflows/pages.yml` is a short recipe GitHub runs for you on every
push: copy the repo, upload the `site/` folder, publish it. YAML is
indentation-sensitive, like Python: a misplaced space changes the meaning.
