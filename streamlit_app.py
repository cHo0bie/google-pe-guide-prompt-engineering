
import os, re, json, glob, requests
import streamlit as st

# Optional: jsonschema for validation
try:
    import jsonschema
    HAS_JSONSCHEMA = True
except Exception:
    HAS_JSONSCHEMA = False

st.set_page_config(page_title="Prompt Engineering Guide — Demo", page_icon="🧠", layout="wide")

st.title("🧠 Prompt Engineering — Конспект + демо")
st.caption("Запуск шаблонов промптов (OpenAI-совместимые API или GigaChat) + опциональная валидация JSON-схемы.")

# ---------------- Providers ----------------

class OpenAICompat:
    def __init__(self, model: str|None=None, base: str|None=None, key: str|None=None):
        self.base = base or os.environ.get("OPENAI_API_BASE") or st.secrets.get("OPENAI_API_BASE", "https://api.openai.com/v1")
        self.key  = key  or os.environ.get("OPENAI_API_KEY")  or st.secrets.get("OPENAI_API_KEY")
        self.model = model or st.secrets.get("OPENAI_MODEL", "gpt-4o-mini")
        if not self.key:
            st.warning("OPENAI_API_KEY не задан (Secrets). Запросы не будут выполняться.")
    def chat(self, prompt: str, temperature: float=0.0) -> str:
        url = f"{self.base}/chat/completions"
        headers = {"Authorization": f"Bearer {self.key}", "Content-Type":"application/json"}
        data = {"model": self.model, "messages":[{"role":"user","content":prompt}], "temperature": temperature}
        r = requests.post(url, headers=headers, json=data, timeout=120)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]

class GigaChat:
    def __init__(self, model: str|None=None):
        self.model = model or st.secrets.get("GIGACHAT_MODEL","GigaChat-Pro")
        self.scope = os.environ.get("GIGACHAT_SCOPE") or st.secrets.get("GIGACHAT_SCOPE","GIGACHAT_API_PERS")
        self.auth_key = os.environ.get("GIGACHAT_AUTH_KEY") or st.secrets.get("GIGACHAT_AUTH_KEY")
        self._token = None
        if not self.auth_key:
            st.warning("GIGACHAT_AUTH_KEY не задан (Secrets). Запросы не будут выполняться.")
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
    def chat(self, prompt: str, temperature: float=0.0) -> str:
        token = self._get_token()
        url = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"
        headers = {"Authorization": f"Bearer {token}","Content-Type":"application/json"}
        payload = {"model": self.model, "messages":[{"role":"user","content":prompt}],"temperature":temperature}
        r = requests.post(url, headers=headers, json=payload, timeout=120, verify=True)
        if r.status_code==401:
            self._token=None
            return self.chat(prompt, temperature=temperature)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]

def get_provider(name: str, model: str|None=None):
    if name=="OpenAI":
        base = st.text_input("OPENAI_API_BASE (опц.)", value=st.secrets.get("OPENAI_API_BASE","https://api.openai.com/v1"))
        key  = st.text_input("OPENAI_API_KEY (если не в Secrets)", type="password", value="")
        return OpenAICompat(model=model, base=base, key=key or None)
    else:
        return GigaChat(model=model)

# --------------- UI: Sidebar ----------------
st.sidebar.header("Провайдер и параметры")
provider_name = st.sidebar.selectbox("Провайдер", ["OpenAI","GigaChat"], index=0)
model = st.sidebar.text_input("Модель", value= "gpt-4o-mini" if provider_name=="OpenAI" else "GigaChat-Pro")
temperature = st.sidebar.slider("Температура", 0.0, 1.2, 0.0, 0.1)

p = get_provider(provider_name, model=model)

st.sidebar.markdown("---")
st.sidebar.subheader("JSON Schema (опционально)")
schemas = sorted(glob.glob("banking/schemas/*.json"))
schema_choice = st.sidebar.selectbox("Схема из репо", ["(нет)"]+schemas, index=0)
schema_upload = st.sidebar.file_uploader("Или загрузить .json", type=["json"])
schema_obj = None
if schema_upload is not None:
    try:
        schema_obj = json.loads(schema_upload.read().decode("utf-8"))
        st.sidebar.success("Схема загружена")
    except Exception as e:
        st.sidebar.error(f"Ошибка чтения схемы: {e}")

# --------------- Pick a prompt --------------
st.subheader("Шаблон промпта")
all_prompts = sorted(glob.glob("prompts/**/*.md", recursive=True))
default_idx = next((i for i,pth in enumerate(all_prompts) if "banking/faq_with_citations.md" in pth), 0) if all_prompts else 0
prompt_file = st.selectbox("Файл", all_prompts, index=default_idx if all_prompts else 0)

prompt_text = ""
if prompt_file:
    with open(prompt_file, "r", encoding="utf-8") as f:
        prompt_text = f.read()

# Поиск переменных {var} (не считаем {{...}})
def find_vars(txt: str):
    # match {var} where not {{var}} and not part of }}
    return sorted(set(m.group(1) for m in re.finditer(r"(?<!\{)\{([a-zA-Z_][a-zA-Z0-9_]*)\}(?!\})", txt)))

vars_found = find_vars(prompt_text)

with st.expander("Показать шаблон", expanded=False):
    st.code(prompt_text, language="markdown")
st.write("Найдены переменные:", ", ".join(vars_found) if vars_found else "нет")

# Поля для переменных
values = {}
cols = st.columns(min(3, max(1,len(vars_found))) or 1)
for i, var in enumerate(vars_found):
    with cols[i % len(cols)]:
        values[var] = st.text_area(var, height=80, value="")

# Сборка промпта
def render_vars(text: str, vars: dict) -> str:
    for k,v in vars.items():
        text = text.replace("{"+k+"}", str(v))
    return text

compiled = render_vars(prompt_text, values) if prompt_text else ""

st.subheader("Скомпилированный промпт")
st.code(compiled[:4000] if compiled else "", language="markdown")

# --------------- Run ----------------
run = st.button("Запустить")
if run and compiled:
    try:
        with st.spinner("Запрос к модели..."):
            out = p.chat(compiled, temperature=temperature)
        st.success("Готово")
        st.subheader("Ответ")
        st.code(out, language="json" if out.strip().startswith("{") else "markdown")

        # Валидация по схеме
        if schema_choice != "(нет)" or schema_obj is not None:
            if not HAS_JSONSCHEMA:
                st.info("Модуль jsonschema не установлен в окружении.")
            else:
                try:
                    if schema_obj is None and schema_choice != "(нет)":
                        with open(schema_choice, "r", encoding="utf-8") as f:
                            schema_obj = json.load(f)
                    # наивное извлечение JSON из ответа
                    s = out[out.find("{"): out.rfind("}")+1]
                    obj = json.loads(s)
                    jsonschema.validate(obj, schema_obj)
                    st.success("JSON валиден по схеме ✅")
                except Exception as e:
                    st.error(f"Ошибка валидации JSON: {e}")
    except Exception as e:
        st.error(f"Ошибка при запросе: {e}")

st.markdown("---")
st.caption("Секреты задаются через Streamlit Secrets: OPENAI_API_KEY/OPENAI_API_BASE или GIGACHAT_AUTH_KEY/GIGACHAT_SCOPE.")
