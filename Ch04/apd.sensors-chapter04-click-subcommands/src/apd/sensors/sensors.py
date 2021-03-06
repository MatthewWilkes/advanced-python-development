#!/usr/bin/env python
# coding: utf-8
import importlib
import math
import socket
import sys
from typing import Any, Optional, List, Tuple, Iterable, TypeVar, Generic


import click
import psutil


T_value = TypeVar("T_value")


class Sensor(Generic[T_value]):
    title: str

    def value(self) -> T_value:
        raise NotImplementedError

    @classmethod
    def format(cls, value: T_value) -> str:
        raise NotImplementedError

    def __str__(self) -> str:
        return self.format(self.value())


class PythonVersion(Sensor[Any]):
    title = "Python Version"

    def value(self) -> Any:
        return sys.version_info

    @classmethod
    def format(cls, value: Any) -> str:
        if value.micro == 0 and value.releaselevel == "alpha":
            return "{0.major}.{0.minor}.{0.micro}a{0.serial}".format(value)
        return "{0.major}.{0.minor}".format(value)


class IPAddresses(Sensor[Iterable[Tuple[str, str]]]):
    title = "IP Addresses"
    FAMILIES = {"AF_INET": "IPv4", "AF_INET6": "IPv6"}

    def value(self) -> List[Tuple[str, str]]:
        hostname = socket.gethostname()
        addresses = socket.getaddrinfo(hostname, None)

        address_info: List[Tuple[str, str]] = []
        for address in addresses:
            family, ip = (address[0].name, address[4][0])
            if family not in self.FAMILIES:
                continue
            value = (family, ip)
            if value not in address_info:
                address_info.append(value)
        return address_info

    @classmethod
    def format(cls, value: Iterable[Tuple[str, str]]) -> str:
        return "\n".join(
            "{0} ({1})".format(address[1], cls.FAMILIES.get(address[0], "Unknown"))
            for address in value
        )


class CPULoad(Sensor[float]):
    title = "CPU Usage"

    def value(self) -> float:
        return psutil.cpu_percent(interval=3) / 100.0

    @classmethod
    def format(cls, value: float) -> str:
        return "{:.1%}".format(value)


class RAMAvailable(Sensor[int]):
    title = "RAM Available"
    UNITS = ("B", "KiB", "MiB", "GiB", "TiB", "PiB", "EiB")
    UNIT_SIZE = 2 ** 10

    def value(self) -> int:
        return psutil.virtual_memory().available

    @classmethod
    def format(cls, value: int) -> str:
        magnitude = math.floor(math.log(value, cls.UNIT_SIZE))
        max_magnitude = len(cls.UNITS) - 1
        magnitude = min(magnitude, max_magnitude)
        scaled_value = value / (cls.UNIT_SIZE ** magnitude)
        return "{:.1f} {}".format(scaled_value, cls.UNITS[magnitude])


class ACStatus(Sensor[Optional[bool]]):
    title = "AC Connected"

    def value(self) -> Optional[bool]:
        battery = psutil.sensors_battery()
        if battery is not None:
            return battery.power_plugged
        else:
            return None

    @classmethod
    def format(cls, value: Optional[bool]) -> str:
        if value is None:
            return "Unknown"
        elif value:
            return "Connected"
        else:
            return "Not connected"


class Temperature(Sensor[Optional[float]]):
    title = "Ambient Temperature"

    def value(self) -> Optional[float]:
        try:
            from adafruit_dht import DHT22
            from board import D20
        except (ImportError, NotImplementedError):
            # No DHT library results in an ImportError.
            # Running on an unknown platform results in a
            # NotImplementedError when getting the pin
            return None
        try:
            return DHT22(D20).temperature
        except RuntimeError:
            return None

    @classmethod
    def celsius_to_fahrenheit(cls, value: float) -> float:
        return value * 9 / 5 + 32

    @classmethod
    def format(cls, value: Optional[float]) -> str:
        if value is None:
            return "Unknown"
        else:
            return "{:.1f}C ({:.1f}F)".format(value, cls.celsius_to_fahrenheit(value))

    def __str__(self) -> str:
        return self.format(self.value())


class RelativeHumidity(Sensor[Optional[float]]):
    title = "Relative Humidity"

    def value(self) -> Optional[float]:
        try:
            from adafruit_dht import DHT22
            from board import D20
        except (ImportError, NotImplementedError):
            # No DHT library results in an ImportError.
            # Running on an unknown platform results in a
            # NotImplementedError when getting the pin
            return None
        try:
            return DHT22(D20).humidity / 100
        except RuntimeError:
            return None

    @classmethod
    def format(cls, value: Optional[float]) -> str:
        if value is None:
            return "Unknown"
        else:
            return "{:.1%}".format(value)


def get_sensors() -> Iterable[Sensor[Any]]:
    return [
        PythonVersion(),
        IPAddresses(),
        CPULoad(),
        RAMAvailable(),
        ACStatus(),
        Temperature(),
        RelativeHumidity(),
    ]


@click.group()
def show_sensors() -> None:
    return


RETURN_CODES = {"OK": 0, "BAD_SENSOR_PATH": 17}


def get_sensor_by_path(sensor_path: str) -> Sensor[Any]:
    try:
        module_name, sensor_name = sensor_path.split(":")
    except ValueError:
        raise RuntimeError(
            "Sensor path must be in the format dotted.path.to.module:ClassName"
        )
    try:
        module = importlib.import_module(module_name)
    except ImportError:
        raise RuntimeError(f"Could not import module {module_name}")
    try:
        sensor_class = getattr(module, sensor_name)
    except AttributeError:
        raise RuntimeError(f"Could not find attribute {sensor_name} in {module_name}")
    if (
        isinstance(sensor_class, type)
        and issubclass(sensor_class, Sensor)
        and sensor_class != Sensor
    ):
        return sensor_class()
    else:
        raise RuntimeError(
            f"Detected object {sensor_class!r} is not recognised as a Sensor type"
        )


@show_sensors.command(help="Displays the values of the sensors")
def show() -> int:
    sensors = get_sensors()
    for sensor in sensors:
        click.secho(sensor.title, bold=True)
        click.echo(str(sensor))
        click.echo("")
    return RETURN_CODES["OK"]


@show_sensors.command(help="Displays the values of a specific sensor in development")
@click.argument("sensor_path", required=True, metavar="path")
def develop(sensor_path) -> int:
    try:
        sensor = get_sensor_by_path(sensor_path)
    except RuntimeError as error:
        click.secho(str(error), fg="red", bold=True)
        return RETURN_CODES["BAD_SENSOR_PATH"]

    click.secho(sensor.title, bold=True)
    click.echo(str(sensor))
    click.echo("")
    return RETURN_CODES["OK"]


if __name__ == "__main__":
    show_sensors()
