# Conferencia Fiscal Flask

Versao web do app da pasta `Teste 4`.

## Rodar localmente

```bash
pip install -r requirements.txt
python app.py
```

Acesse `http://127.0.0.1:5002`.

## Subir em servidor Linux

Envie estes arquivos/pastas:

- `app.py`
- `conferência.py` (atalho local opcional)
- `conferencia_core.py`
- `wsgi.py`
- `templates/`
- `requirements.txt`

Instale e rode:

```bash
pip install -r requirements.txt
gunicorn wsgi:app --bind 0.0.0.0:8000
```

Em painel WSGI, use `wsgi:app`.

## Funcionalidades

- NF-e Modelo 55: Excel SAT x PDF Registro de Entradas.
- CTe: Excel SAT x PDF Registro de Entradas.
- Comparacao Teste: arquivo Teste x arquivo RPT.
- Exportacao Excel com as mesmas abas do app desktop.

Uploads e resultados temporarios ficam em `instance/`.
