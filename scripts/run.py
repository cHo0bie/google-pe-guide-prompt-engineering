#!/usr/bin/env python3
import os, sys, json, time, typing as T
import typer, requests
from rich import print
from dotenv import load_dotenv

app = typer.Typer(add_help_option=True)

def load_prompt(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def render_vars(text: str, vars: T.Dict[str,str]) -> str:
    for k,v in vars.items():
        text = text.replace("{"+k+"}", str(v))
    return text

# --- Providers ---

class OpenAICompat:
    def __init__(self, model: str|None=None):
        self.base = os.environ.get("OPENAI_API_BASE","https://api.openai.com/v1")
        self.key = os.environ["OPENAI_API_KEY"]
        self.model = model or "gpt-4o-mini"
    def chat(self, prompt: str) -> str:
        url = f"{self.base}/chat/completions"
        headers = {"Authorization": f"Bearer {self.key}", "Content-Type":"application/json"}
        data = {"model": self.model, "messages":[{"role":"user","content":prompt}], "temperature":0}
        r = requests.post(url, headers=headers, json=data, timeout=120)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]

class GigaChat:
    def __init__(self, model: str|None=None):
        self.model = model or "GigaChat-Pro"
        self.scope = os.environ.get("GIGACHAT_SCOPE","GIGACHAT_API_PERS")
        self.client_id = os.environ["GIGACHAT_CLIENT_ID"]
        self.auth_key = os.environ["GIGACHAT_AUTH_KEY"]
        self._token = None
    def _token_headers(self):
        return {"Authorization": f"Basic {self.auth_key}","Content-Type":"application/x-www-form-urlencoded"}
    def _get_token(self)->str:
        if self._token: return self._token
        url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
        data = {"scope": self.scope}
        r = requests.post(url, headers=self._token_headers(), data=data, timeout=60, verify=True)
        r.raise_for_status()
        self._token = r.json()["access_token"]
        return self._token
    def chat(self, prompt: str) -> str:
        token = self._get_token()
        url = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"
        headers = {"Authorization": f"Bearer {token}","Content-Type":"application/json"}
        payload = {"model": self.model, "messages":[{"role":"user","content":prompt}],"temperature":0}
        r = requests.post(url, headers=headers, json=payload, timeout=120, verify=True)
        if r.status_code==401:
            self._token=None
            return self.chat(prompt)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]

def get_provider(name: str, model: str|None=None):
    if name=="openai":
        return OpenAICompat(model=model)
    elif name=="gigachat":
        return GigaChat(model=model)
    raise ValueError("Unknown provider: "+name)

@app.command()
def chat(prompt_file: str, model: str = typer.Option(None),
         schema: str = typer.Option(None, help='Путь к JSON Schema для валидации ответа'),
         var: list[str] = typer.Option(None, help="Пара key=value для подстановки")):
    """
    Простой прогон любого markdown‑шаблона промпта.
    Переменные {var} в файле заменяются значениями из --var key=value
    """
    load_dotenv()
    provider = os.environ.get("PROVIDER","openai")
    p = get_provider(provider, model=model)
    text = load_prompt(prompt_file)
    kv = {}
    if var:
        for pair in var:
            k,v = pair.split("=",1)
            kv[k]=v
    text = render_vars(text, kv)
    print("[bold]Промпт:[/bold]\n", text[:1000], "\n---")
    out = p.chat(text)
    # Печать ответа
    print("[bold green]Ответ:[/bold green]\n", out)
    # Валидация JSON, если указана схема
    if schema:
        try:
            import json, re, jsonschema
            # Наивное извлечение JSON из ответа
            s = out[out.find('{'): out.rfind('}')+1]
            obj = json.loads(s)
            with open(schema, 'r', encoding='utf-8') as sf:
                sch = json.load(sf)
            jsonschema.validate(obj, sch)
            print("[bold cyan]JSON валиден по схеме[/bold cyan]")
        except Exception as e:
            print("[bold red]Ошибка валидации JSON:[/bold red]", e)

if __name__ == "__main__":
    app()
