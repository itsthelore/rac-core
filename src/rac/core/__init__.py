"""RAC core layer.

The domain and specification primitives that know nothing about the CLI, terminal
formatting, or Explorer: artifact models, Markdown parsing, classification,
validation, artifact specs, schema references, and filesystem discovery.
Consumers import the submodules directly (``rac.core.markdown``, ``rac.core.fs``,
and so on); this package root deliberately exports nothing.
"""
