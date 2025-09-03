
import os, re, json, glob, requests, time, base64, io
import streamlit as st

# Optional: jsonschema for validation
try:
    import jsonschema
    HAS_JSONSCHEMA = True
except Exception:
    HAS_JSONSCHEMA = False

st.set_page_config(page_title="Prompt Engineering — Lab", page_icon="🧠", layout="wide")

# ---------------- Session helpers ----------------
def _init_state():
    ss = st.session_state
    ss.setdefault("history", [])  # list of dicts
    ss.setdefault("custom_prompts", {})  # name -> text
    ss.setdefault("cot_builder", {"system":"Ты — аккуратный аналитик.",
                                  "role":"Исследователь в банковском домене РФ.",
                                  "context":"Платформа: мобильный банкинг 2024–2025. Отвечай фактами, избегай галлюцинаций.",
                                  "task":"Сформируй краткий ответ (1–3 предложения). Если данных нет — верни 'N/A'."})
    ss.setdefault("last_response", None)
_init_state()

def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%S")

def add_history(entry: dict):
    st.session_state.history.insert(0, entry)

def download_bytes(name: str, data: bytes, label: str):
    st.download_button(label, data=data, file_name=name, mime="application/octet-stream")

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

def get_provider(name, model=None):
    return GigaChat(model=model)

# --------------- Sidebar: provider & params --------------
st.sidebar.header("Провайдер и параметры")
st.sidebar.text_input("Провайдер", value="GigaChat", disabled=True)
model = st.sidebar.text_input("Модель", value="GigaChat-Pro", disabled=True)
temperature = st.sidebar.slider("Температура", 0.0, 1.2, 0.0, 0.1)
p = GigaChat(model=model)

st.sidebar.markdown("---")
st.sidebar.subheader("JSON Schema (опционально)")
import glob as _glob
schemas = sorted(_glob.glob("banking/schemas/*.json"))
schema_choice = st.sidebar.selectbox("Схема из репо", ["(нет)"]+schemas, index=0)
schema_upload = st.sidebar.file_uploader("Или загрузить .json", type=["json"])
schema_obj = None
schema_name = None
if schema_upload is not None:
    try:
        schema_data = schema_upload.read().decode("utf-8")
        schema_obj = json.loads(schema_data)
        schema_name = f"upload:{schema_upload.name}"
        st.sidebar.success("Схема загружена")
    except Exception as e:
        st.sidebar.error(f"Ошибка чтения схемы: {e}")
elif schema_choice != "(нет)":
    schema_name = schema_choice

# ---------------- Tabs ----------------
tab_run, tab_builder, tab_history, tab_custom = st.tabs(["▶️ Запуск", "🧩 CoT/Step‑back Builder", "🕓 История", "📥 Свои шаблоны"])

# ---------------- RUN TAB ----------------
with tab_run:
    st.subheader("Шаблон промпта")
    all_prompts = sorted(_glob.glob("prompts/**/*.md", recursive=True))
    # include custom prompts
    if st.session_state.custom_prompts:
        for name in st.session_state.custom_prompts.keys():
            all_prompts.append(f"custom://{name}")
    default_idx = next((i for i,pth in enumerate(all_prompts) if "banking/faq_with_citations.md" in pth), 0) if all_prompts else 0
    prompt_file = st.selectbox("Файл", all_prompts, index=default_idx if all_prompts else 0)

    # select source text
    if prompt_file.startswith("custom://"):
        pname = prompt_file.replace("custom://","")
        prompt_text = st.session_state.custom_prompts.get(pname,"")
    else:
        prompt_text = ""
        if prompt_file:
            with open(prompt_file, "r", encoding="utf-8") as f:
                prompt_text = f.read()

    # detect variables
    def find_vars(txt: str):
        return sorted(set(m.group(1) for m in re.finditer(r"(?<!\{)\{([a-zA-Z_][a-zA-Z0-9_]*)\}(?!\})", txt)))
    vars_found = find_vars(prompt_text)

    with st.expander("Показать шаблон", expanded=False):
        st.code(prompt_text, language="markdown")
    st.write("Найдены переменные:", ", ".join(vars_found) if vars_found else "нет")

    values = {}
    cols = st.columns(min(3, max(1,len(vars_found))) or 1)
    for i, var in enumerate(vars_found):
        with cols[i % len(cols)]:
            values[var] = st.text_area(var, height=80, value="")

    def render_vars(text: str, vars: dict) -> str:
        for k,v in vars.items():
            text = text.replace("{"+k+"}", str(v))
        return text

    compiled = render_vars(prompt_text, values) if prompt_text else ""
    st.subheader("Скомпилированный промпт")
    st.code(compiled[:5000] if compiled else "", language="markdown")

    run = st.button("Запустить", type="primary")
    if run and compiled:
        try:
            with st.spinner("Запрос к модели..."):
                out = p.chat(compiled, temperature=temperature)
            st.success("Готово")
            st.subheader("Ответ")
            st.code(out, language="json" if out.strip().startswith("{") else "markdown")

            valid_status = None
            if (schema_choice != "(нет)" or schema_obj is not None):
                if not HAS_JSONSCHEMA:
                    st.info("Модуль jsonschema не установлен в окружении.")
                else:
                    try:
                        s = out[out.find("{"): out.rfind("}")+1]
                        obj = json.loads(s)
                        if schema_obj is None:
                            with open(schema_choice, "r", encoding="utf-8") as f:
                                schema_obj_local = json.load(f)
                        else:
                            schema_obj_local = schema_obj
                        jsonschema.validate(obj, schema_obj_local)
                        st.success("JSON валиден по схеме ✅")
                        valid_status = True
                    except Exception as e:
                        st.error(f"Ошибка валидации JSON: {e}")
                        valid_status = False

            # push to history
            add_history({
                "ts": now_iso(),
                "provider": 'GigaChat',
                "model": model,
                "temperature": temperature,
                "template": prompt_file,
                "variables": values,
                "compiled": compiled,
                "response": out,
                "schema": schema_name,
                "valid": valid_status
            })
            st.session_state.last_response = out
        except Exception as e:
            st.error(f"Ошибка при запросе: {e}")

# ---------------- BUILDER TAB ----------------
with tab_builder:
    st.subheader("CoT/Step‑back Builder — конструктор промптов")
    b = st.session_state.cot_builder
    c1, c2 = st.columns(2)
    with c1:
        b["system"] = st.text_area("System", value=b.get("system",""), height=120)
        b["role"]   = st.text_area("Role", value=b.get("role",""), height=100)
        b["context"]= st.text_area("Context (факты/ограничения)", value=b.get("context",""), height=150)
    with c2:
        b["task"]   = st.text_area("Task (задание + формат вывода)", value=b.get("task",""), height=180)
        add_stepback = st.checkbox("Добавить Step‑back (принципы → решение)", value=True)
        include_cot = st.checkbox("Включить подсказку к CoT (скрытую)", value=True)

    # Assemble preview
    template = "[system] {system}\n[role] {role}\n[context] {context}\n\nЗадание:\n{task}\n"
    if add_stepback:
        template += "\nШаг 1 — сформулируй 1–3 общих принципа / допущения.\nШаг 2 — выполни задание с учётом принципов.\n"
    if include_cot:
        template += "\n(Подумай шагами, но верни только финальный ответ.)\n"

    compiled_builder = template.format(**b)
    st.markdown("#### Превью собранного промпта")
    st.code(compiled_builder, language="markdown")

    c3, c4 = st.columns(2)
    with c3:
        name = st.text_input("Сохранить как (имя шаблона)", value="builder_prompt.md")
        if st.button("Добавить в список шаблонов"):
            st.session_state.custom_prompts[name] = compiled_builder
            st.success(f"Добавлено: custom://{name}")
    with c4:
        st.download_button("Скачать .md", compiled_builder.encode("utf-8"), file_name=name or "builder_prompt.md")

# ---------------- HISTORY TAB ----------------
with tab_history:
    st.subheader("История сессии")
    if not st.session_state.history:
        st.info("История пуста — запустите хотя бы один промпт.")
    else:
        for i, item in enumerate(st.session_state.history):
            with st.expander(f"{item['ts']} · {item['provider']}:{item['model']} · {item['template']} (val={item['valid']})", expanded=False):
                st.markdown("**Vars:** " + json.dumps(item['variables'], ensure_ascii=False))
                st.markdown("**Prompt:**")
                st.code(item['compiled'], language="markdown")
                st.markdown("**Response:**")
                st.code(item['response'], language="json" if str(item['response']).strip().startswith("{") else "markdown")
        # Export/Import
        st.markdown("---")
        export = json.dumps(st.session_state.history, ensure_ascii=False, indent=2).encode("utf-8")
        download_bytes("history.json", export, "Скачать историю (JSON)")
        imported = st.file_uploader("Импорт истории (JSON)", type=["json"])
        if imported is not None:
            try:
                data = json.loads(imported.read().decode("utf-8"))
                if isinstance(data, list):
                    st.session_state.history = data + st.session_state.history
                    st.success("История импортирована")
            except Exception as e:
                st.error(f"Импорт не удался: {e}")
        if st.button("Очистить историю"):
            st.session_state.history.clear()
            st.experimental_rerun()

# ---------------- CUSTOM TEMPLATES TAB ----------------
with tab_custom:
    st.subheader("Добавить свои шаблоны")
    up = st.file_uploader("Загрузить .md шаблон(ы)", type=["md"], accept_multiple_files=True)
    if up:
        for f in up:
            try:
                txt = f.read().decode("utf-8")
                st.session_state.custom_prompts[f.name] = txt
                st.success(f"Добавлен: custom://{f.name}")
            except Exception as e:
                st.error(f"{f.name}: {e}")
    st.markdown("Текущее количество кастомных: **{}**".format(len(st.session_state.custom_prompts)))
    if st.session_state.custom_prompts:
        with st.expander("Показать список", expanded=False):
            for k,v in st.session_state.custom_prompts.items():
                st.markdown(f"**custom://{k}**")
                st.code(v, language="markdown")
    if st.button("Очистить кастомные шаблоны"):
        st.session_state.custom_prompts.clear()
        st.experimental_rerun()

st.markdown("---")
st.caption("Советы: сохраняйте эксперименты в историю и выгружайте JSON. Секреты: OPENAI_API_KEY/BASE, GIGACHAT_AUTH_KEY/SCOPE.")
