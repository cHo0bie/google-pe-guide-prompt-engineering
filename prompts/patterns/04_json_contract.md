# Строгий JSON‑вывод
Верни строго валидный JSON согласно схеме.
Схема:
{{
  "type":"object",
  "properties":{{"entities":{{"type":"array","items":{{"type":"string"}}}}}},
  "required":["entities"],
  "additionalProperties":false
}}

Текст: {text}
Ответ (только JSON):
