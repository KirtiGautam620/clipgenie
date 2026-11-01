"""Photo Story (prototype, Tier A): turn photos into a video from ONE description of the project.

Nothing in this package runs FFmpeg, a model or the network. It only
  - checks and describes a project (manifest.py),
  - works out how a photo should move (motion.py) and how long things last (timing.py),
  - writes the FFmpeg commands as plain lists of text, ready to run later (graph.py),
  - and tidies uploaded photos (ingest.py, the only part that opens image files).

The existing finishing layers (captions, headline, music, voice levelling) are reused as they are.
"""
