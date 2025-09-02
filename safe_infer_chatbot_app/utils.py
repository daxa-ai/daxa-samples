import os

import requests


def get_available_models():
    try:
        headers = {
            'accept': 'application/json',
            'Authorization': f"Bearer {os.environ.get('PEBBLO_API_KEY')}",
            'Content-Type': 'application/x-www-form-urlencoded',
        }
        url = f"{os.environ.get('PROXIMA_HOST')}/safe_infer/llm/provider/list"
        response = requests.get(url, headers=headers)
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
