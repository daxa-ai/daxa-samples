import os

import requests

def convert_to_dict(obj):
    """
    Recursively convert any object (including nested dictionaries, objects, etc.)
    to a regular Python dictionary.
    """
    if obj is None:
        return None
    elif isinstance(obj, (str, int, float, bool)):
        return obj
    elif isinstance(obj, dict):
        return {key: convert_to_dict(value) for key, value in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [convert_to_dict(item) for item in obj]
    elif hasattr(obj, 'model_dump'):
        # For Pydantic models (try this first as it's most reliable)
        try:
            return convert_to_dict(obj.model_dump())
        except Exception as e:
            print(f"Error with model_dump: {e}")
    elif hasattr(obj, '_asdict'):
        # For namedtuples
        try:
            return convert_to_dict(obj._asdict())
        except Exception as e:
            print(f"Error with _asdict: {e}")
    elif hasattr(obj, 'dict'):
        # For some other object types that have dict() method
        try:
            return convert_to_dict(obj.dict())
        except Exception as e:
            print(f"Error with dict(): {e}")
    elif hasattr(obj, '__dict__'):
        # For objects with __dict__ attribute
        try:
            return convert_to_dict(obj.__dict__)
        except Exception as e:
            print(f"Error with __dict__: {e}")
    elif hasattr(obj, '__iter__') and not isinstance(obj, (str, bytes)):
        # For other iterable objects
        try:
            return [convert_to_dict(item) for item in obj]
        except Exception as e:
            print(f"Error with iteration: {e}")
    else:
        # For objects that can't be converted, try to get their string representation
        try:
            # Try to get all attributes
            if hasattr(obj, '__slots__'):
                # For objects with __slots__
                return {slot: convert_to_dict(getattr(obj, slot, None)) for slot in obj.__slots__}
            else:
                # For other objects, try to convert to string or return type info
                return str(obj)
        except Exception as e:
            print(f"Error converting object {type(obj)}: {e}")
            return f"<{type(obj).__name__} object>"

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
