"""The creator assistant: understands a request, picks a real tool, plans it, runs it, reports back.

    tools.py      what the assistant can actually do (and, for the rest, why it cannot yet)
    router.py     request -> tool + arguments (fixed rules first, the local model only when unclear)
    ideas.py      the Video ideas tool (grounded in the user's own video)
    workflows.py  a saved, step-by-step run of a tool, with progress; one heavy job at a time
    store.py      where conversations and workflows are kept
    api.py        the HTTP endpoints

The assistant never invents an answer: every reply is either a tool's real result, a fixed sentence
about what it is doing, or an honest "not available yet" with the reason.
"""
