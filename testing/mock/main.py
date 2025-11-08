import requests


def get_weather(city):
    res = requests.get(f"https://api.weather.com/v1/{city}")
    if res.status_code == 200:
        return res.json()
    else:
        return ValueError("Could not fetch weather data")
