"""AI Storyboard (MVP): turn one photo and a prompt into a shot plan you can edit and take elsewhere.

What this package really does, and does not do:
  - It builds a SHOT PLAN from templates and the words in the prompt (planner.py). It is rule-based,
    not AI: the same prompt always gives the same plan.
  - It draws real preview frames by cropping and reframing the user's OWN photo (frames.py). These show
    composition and zoom, never a new camera angle or new content.
  - It writes a prompt for each scene that can be pasted into an external video generator (prompts.py).
Nothing here runs an AI model, the network, or FFmpeg, and nothing is called "AI generated".
"""
