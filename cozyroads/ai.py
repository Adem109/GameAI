"""DeepSeek-powered villager brains.

Requests run on background threads so the game never freezes. Each request
returns a dict {"reply": str, "action": dict | None}. Without an API key (or
when the network fails) a small offline brain answers instead, so the game is
always playable.
"""
import json
import queue
import random
import ssl
import threading
import urllib.error
import urllib.request

ITEMS = ["carrot", "tomato", "pumpkin"]
GIFTABLE = ["carrot_seed", "tomato_seed", "pumpkin_seed", "coins"]

ACTION_SPEC = """You may attach at most ONE action that changes the game world:
- {"type":"give_quest","item":"carrot|tomato|pumpkin","amount":1-5,"reward":5-80}  ask the player to bring you crops
- {"type":"gift","item":"carrot_seed|tomato_seed|pumpkin_seed|coins","amount":1-10}  give the player something small
- {"type":"walk_to","place":"<one of PLACES>"}  walk somewhere yourself (e.g. when invited)
- {"type":"follow_player"}  walk along with the player for a while
- {"type":"challenge","place":"<one of PLACES>","seconds":15-90,"reward":5-40}  challenge the player to run or drive there in time
Use actions sparingly and only when they fit the conversation. Otherwise use null."""


def build_system_prompt(npc, world_state: dict) -> str:
    return f"""You are {npc.name}, a villager in the cozy, relaxing game "Cozy Roads".
Personality: {npc.personality}
You live in a small countryside village with roads, a farm, a pond and a market.
The player can walk, run, drive a car, and farm carrots, tomatoes and pumpkins.

Current game state:
{json.dumps(world_state, indent=1)}

PLACES: {", ".join(world_state.get("places", []))}

Rules:
- Stay in character. Be warm, calm and playful. Replies under 45 words.
- Never mention being an AI or a language model.
- React to the game state (time of day, weather, what the player carries, quests).

{ACTION_SPEC}

Respond ONLY with JSON: {{"reply": "<what you say>", "action": <action object or null>}}"""


def _ssl_context():
    """python.org's macOS Python (and PyInstaller apps) often lack root certificates;
    certifi's bundle makes HTTPS work out of the box."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


SSL_CONTEXT = _ssl_context()


class DeepSeekClient:
    def __init__(self, api_key: str, model: str, base_url: str):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.results: "queue.Queue[tuple]" = queue.Queue()

    @property
    def online(self) -> bool:
        return bool(self.api_key)

    def request(self, tag, system_prompt: str, history: list, user_text: str, max_tokens=220):
        """Fire a request; the result later appears in self.results as (tag, dict)."""
        messages = [{"role": "system", "content": system_prompt}]
        messages += history[-12:]
        messages.append({"role": "user", "content": user_text})
        threading.Thread(
            target=self._worker, args=(tag, messages, max_tokens), daemon=True
        ).start()

    def _worker(self, tag, messages, max_tokens):
        try:
            result = self._call(messages, max_tokens)
        except Exception as exc:  # network, HTTP, JSON - fall back gracefully
            result = {"reply": None, "action": None, "error": _describe_error(exc)}
        self.results.put((tag, result))

    def _call(self, messages, max_tokens):
        body = json.dumps({
            "model": self.model,
            "messages": messages,
            "temperature": 1.0,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }).encode()
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
        )
        with urllib.request.urlopen(req, timeout=30, context=SSL_CONTEXT) as resp:
            data = json.loads(resp.read().decode())
        content = data["choices"][0]["message"]["content"]
        return parse_reply(content)

    def poll(self):
        out = []
        while True:
            try:
                out.append(self.results.get_nowait())
            except queue.Empty:
                return out


def _describe_error(exc) -> str:
    if isinstance(exc, urllib.error.HTTPError):
        if exc.code == 401:
            return "DeepSeek rejected the API key (401)."
        if exc.code == 402:
            return "DeepSeek account has insufficient balance (402)."
        return f"DeepSeek HTTP error {exc.code}."
    if isinstance(exc, urllib.error.URLError):
        reason = exc.reason
        if isinstance(reason, ssl.SSLCertVerificationError):
            return "Secure connection failed (missing certificates). Run: pip install certifi"
        return f"Could not reach DeepSeek: {reason}"
    if isinstance(exc, TimeoutError):
        return "DeepSeek took too long to answer. Try again."
    return f"AI error: {exc.__class__.__name__}"


def parse_reply(content: str) -> dict:
    try:
        obj = json.loads(content)
    except ValueError:
        # Model ignored JSON mode: treat the whole thing as speech.
        return {"reply": content.strip()[:300], "action": None}
    reply = str(obj.get("reply", "")).strip()[:300] or "..."
    action = obj.get("action")
    return {"reply": reply, "action": action if isinstance(action, dict) else None}


# --------------------------------------------------------------------------
# Offline brain: used when no API key is configured or a request fails.

OFFLINE_GREETINGS = {
    "Mira": ["Morning! The soil smells great today.", "Watered your crops yet?", "Pumpkins love patience."],
    "Ben": ["That car purrs like a kitten.", "Mind the curves on the east road!", "Need a tune-up? Ha, just kidding."],
    "Juno": ["Race you to the pond!", "Running clears the head.", "Nice pace, friend!"],
}


def offline_reply(npc, user_text: str, places: list) -> dict:
    text = user_text.lower()
    if npc.name == "Juno" and random.random() < 0.5:
        place = random.choice(places)
        return {
            "reply": f"Bet you can't reach the {place} in 40 seconds! Go!",
            "action": {"type": "challenge", "place": place, "seconds": 40, "reward": 15},
        }
    if any(w in text for w in ("quest", "help", "job", "work", "need")):
        item = random.choice(ITEMS)
        amount = random.randint(1, 3)
        return {
            "reply": f"Could you bring me {amount} {item}{'s' if amount > 1 else ''}? I'll pay you well.",
            "action": {"type": "give_quest", "item": item, "amount": amount, "reward": 12 * amount},
        }
    if any(w in text for w in ("follow", "come", "walk with")):
        return {"reply": "Sure, lead the way!", "action": {"type": "follow_player"}}
    lines = OFFLINE_GREETINGS.get(npc.name, ["Lovely day, isn't it?"])
    return {
        "reply": random.choice(lines) + " (Add a DeepSeek key in Settings for real conversations.)",
        "action": None,
    }
