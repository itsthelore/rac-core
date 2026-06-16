# Set up your corpus

A RAC corpus is just Markdown under `rac/`, identified by a `.rac/config.yaml`.

**Set Up Workspace** runs `rac quickstart` in this folder, which:

- establishes the repository identity (`.rac/config.yaml`), and
- scaffolds a first artifact you can edit.

The extension computes none of this itself — `rac` owns the identity and the
templates. Once the corpus exists, the extension activates automatically and
starts validating.

> Already set up? The command will tell you, and leave your corpus untouched.
