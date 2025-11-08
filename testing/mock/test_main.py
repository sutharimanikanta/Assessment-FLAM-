from main import get_weather


def test(mocker):
    mg = mocker.patch("main.requests.get")
    mg.return_value.status_code = 200
    mg.return_value.json.return_value = {"weather": "sunny"}
    result = get_weather("London")
    assert result == {"weather": "sunny"}
    mg.assert_called_once_with("https://api.weather.com/London")
