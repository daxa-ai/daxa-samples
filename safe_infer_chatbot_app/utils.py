import os

import requests

def get_proxima_cookie():
    try:
        proxima_url = f"{os.environ.get('PROXIMA_HOST')}/api/auth/login"
        headers = {
            'accept': 'application/json',
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        data = {
            "username": os.environ.get("PROXIMA_USER_USERNAME"),
            "password": os.environ.get("PROXIMA_USER_PASSWORD")
        }
        response = requests.post(proxima_url, headers=headers, data=data)

        response.raise_for_status()

        token = response.headers['set-cookie'].split(';')[0]
        return token
    except Exception as e:
        print(f"Error getting proxima cookie: {e}")
        raise e



def get_available_models():
    try:
        proxima_cookie = get_proxima_cookie()
        headers = {
            'accept': 'application/json',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Cookie': f"fastapiusersauth={proxima_cookie}"
        }
        response = requests.get(f"{os.environ.get('PROXIMA_HOST')}/api/llm/provider", headers=headers)
        response.raise_for_status()
        models = response.json()
        if len(models) == 0:
            return [], ""
        model_names = [model['default_model_name'] for model in models]

        default_model_name = next(model for model in models if model['is_default_provider'])['default_model_name']
        return model_names, default_model_name
    except Exception as e:
        print(f"Error getting available models: {e}")
        raise e
