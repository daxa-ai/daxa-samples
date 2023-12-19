### Instructions

1. Create Python virtual-env


```console
$ python3 -m venv .venv
$ source .venv/bin/activate
```

2. Install dependencies

```console
$ pip3 install -r requirements.txt
```

3. Install `daxa_langchain` python package. You can download this package from your Daxa dashboard Profile at the top right hand corner, `API Key & Packages` page


```console
$ pip3 install ~/Downloads/daxa_langchain-0.1.3-py3-none-any.whl
```


4. Populate `OPENAI_API_KEY` and `DAXA_API_KEY` in .env file. You can download `DAXA_API_KEY` from your Profile at the top right hand corner, `API Key & Packages` page

```console
$ cat .env
OPENAI_API_KEY=""
DAXA_API_KEY=""
```

5. Run langchain sample app _without_ Daxa protection and make sure it successfully produces a valid response.

```console
$ python3 restricted_entities_nodaxa.py
```

6. Run langchain sample app _with_ Daxa protection

```console
$ python3 restricted_entities_withdaxa.py
```

7. Head back to Daxa dashboard to explore visibility, governance and protection features of Daxa at https://app.daxa.ai