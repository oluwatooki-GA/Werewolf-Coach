"""Model calls and the cost ledger. The only place paid calls are made."""

import os

# Use LiteLLM's bundled price list: no network at import, same prices on every machine.
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
