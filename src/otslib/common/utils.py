import os
import subprocess
from collections.abc import Callable
from pathlib import Path
import requests
import json
import hashlib
import time
from ..common.formating import sanitize_string
from typing import Union, Optional
from copy import deepcopy

GENRES = {
    "acoustic", "afrobeat", "alt-rock", "alternative",
    "ambient", "anime", "black-metal", "bluegrass",
    "blues", "bossanova", "brazil", "breakbeat",
    "british", "cantopop", "chicago-house", "children",
    "chill", "classical", "club", "comedy",
    "country", "dance", "dancehall", "death-metal",
    "deep-house", "detroit-techno", "disco", "disney",
    "drum-and-bass", "dub", "dubstep", "edm",
    "electro", "electronic", "emo", "folk",
    "forro", "french", "funk", "garage",
    "german", "gospel", "goth", "grindcore",
    "groove", "grunge", "guitar", "happy",
    "hard-rock", "hardcore", "hardstyle", "heavy-metal",
    "hip-hop", "holidays", "honky-tonk",
    "house", "idm", "indian", "indie",
    "indie-pop", "industrial", "iranian", "j-dance",
    "j-idol", "j-pop", "j-rock", "jazz",
    "k-pop", "kids", "latin", "latino",
    "malay", "mandopop", "metal", "metal-misc",
    "metalcore", "minimal-techno", "movies", "mpb",
    "new-age", "new-release", "opera", "pagode",
    "party", "philippines-opm", "piano", "pop",
    "pop-film", "post-dubstep", "power-pop", "progressive-house",
    "psych-rock", "punk", "punk-rock", "r-n-b",
    "rainy-day", "reggae", "reggaeton", "road-trip",
    "rock", "rock-n-roll", "rockabilly",
    "romance", "sad", "salsa", "samba",
    "sertanejo", "show-tunes", "singer-songwriter",
    "ska", "sleep", "songwriter", "soul",
    "soundtracks", "spanish", "study", "summer",
    "swedish", "synth-pop", "tango", "techno",
    "trance", "trip-hop", "turkish", "work-out", "world-music"
}

def flatten_dictionary(input_dict, parent_key='', sep='_'):
    """
    Recursively flattens a nested dictionary by concatenating keys using a specified separator.

    Parameters:
    - input_dict (dict): The input dictionary to be flattened.
    - parent_key (str, optional): The concatenated key from the parent dictionary. Default is an empty string.
    - sep (str, optional): The separator used between keys when concatenating. Default is an underscore ('_').

    Returns:
    dict: A new dictionary with flattened keys.
    """
    flattened_dict = {}

    for key, value in input_dict.items():
        new_key = f"{parent_key}{sep}{key}" if parent_key else key

        if isinstance(value, dict):
            flattened_dict.update(flatten_dictionary(value, new_key, sep))
        else:
            flattened_dict[new_key] = value

    return flattened_dict


def cached_request(cache_dir: Union[str, None], lifetime: int,
                   get_header_func: Optional[Callable] = None,
                   *args, **kwargs) -> str:
    """
    Call requests.get() while caching the text response to cache directory
    :param cache_dir: Where cache should be stored, None disables the cache
    :param lifetime: Time in seconds up to which cache is valid from now,
                    0 sets unlimited lifetime
    :param get_header_func: Function used to get additional headers
    :param args: Args sent to requests.get()
    :param kwargs: Extra parameters sent to requests.get()
    :return: String response
    """
    # Initialize headers
    headers = kwargs.pop('headers', {}).copy()  # Create a copy to avoid modifying input

    # Handle get_header_func
    if get_header_func is None:
        def get_header_func(): return {}

    # Check if caching is disabled
    if cache_dir is None or os.environ.get('OTSLIB_DISABLE_CACHE', '0') == '1':
        headers.update(get_header_func())
        kwargs['headers'] = headers
        return requests.get(*args, **kwargs).text

    # Generate cache hash
    kwargs_sig = json.dumps(kwargs, sort_keys=True)  # sort_keys for consistent ordering
    args_hash = hashlib.sha224(
        f'{str(args)}:{kwargs_sig}'.encode()
    ).hexdigest()
    print(
        'Cache HASH : ',
        args_hash,
        '\t',
        f'{str(args)}:{kwargs_sig}'
    )
    cache_dir = os.path.join(os.path.abspath(cache_dir), 'api_cache')
    os.makedirs(cache_dir, exist_ok=True)
    cache_file = os.path.join(cache_dir, f'{args_hash}.acache')

    # Check cache if it exists and is valid
    if os.path.isfile(cache_file):
        with open(cache_file, 'r', encoding='utf-8') as cache:
            try:
                expiry_time = int(cache.readline())
                if lifetime == 0 or expiry_time >= int(time.time()):
                    return cache.read().strip()
            except (ValueError, IndexError):
                pass  # Cache file corrupted, proceed with fresh request

    # Make the request
    headers.update(get_header_func())
    kwargs['headers'] = headers
    request = requests.get(*args, **kwargs)

    # Cache if successful
    if 200 <= request.status_code < 300:
        try:
            with open(cache_file, 'w', encoding='utf-8') as cache:
                expiry = int(time.time()) + lifetime if lifetime != 0 else 0
                cache.write(f"{expiry}\n{request.text.strip()}")
        except OSError as e:
            pass
    return request.text

def convert_from_ogg(ffmpeg_path: str, source_media: str, bitrate: int,
                     extra_params: Union[list, None] = None) -> os.PathLike:
    """
    Converts spotify Ogg Vorbis streams to another format via ffmpeg, Note: source media should use the target file
    extension, the source media is assumed Ogg Vorbis regardless of the source media extension
    :param ffmpeg_path: Path to ffmpeg binary
    :param source_media: Path of media to convert
    :param bitrate: Target bitrate of converted media
    :param extra_params: List of extra parameters passed to ffmpeg
    :return: Absolute path to converted media ( Same as source_media, but now it's converted )
    """
    if extra_params is None:
        extra_params: list = []
    if os.path.isfile(os.path.abspath(source_media)):
        target_path: Path = Path(source_media)
        temp_name: str = os.path.join(target_path.parent, ".~" + target_path.stem + ".ogg")
        if os.path.isfile(temp_name):
            os.remove(temp_name)
        os.rename(source_media, temp_name)
        # Prepare default parameters
        command: list = [
            ffmpeg_path,
            '-i', sanitize_string(
                temp_name,
                skip_path_seps=True,
                escape_quotes=False
            )
        ]
        # If the media format is set to ogg, just correct the downloaded file
        # and add tags
        if target_path.suffix == '.ogg':
            command = command + ['-c', 'copy']
        else:
            command = command + ['-ar', '44100', '-ac', '2', '-b:a', f'{bitrate}k']
        if int(os.environ.get('SHOW_FFMPEG_OUTPUT', 0)) == 0:
            command = command + \
                      ['-loglevel', 'error', '-hide_banner', '-nostats']
        # Add user defined parameters
        for param in extra_params:
            command.append(param)
        # Add output parameter at last
        command.append(
            sanitize_string(
                source_media,
                skip_path_seps=True,
                escape_quotes=False
            )
        )
        subprocess.check_call(command, shell=False)
        os.remove(temp_name)
        return target_path
    else:
        raise FileNotFoundError


def pick_thumbnail(covers: list[dict], preferred_size: int = 640000) -> str:
    """
    Returns url for the artwork from available artworks
    :param covers: list of dict containing artwork/thumbnail info
    :param preferred_size: Size of media (width*height) which will be returned or next available better one
    :return: Url of the cover art for media
    """
    images = {}
    for image in covers:
        try:
            images[image['height'] * image['width']] = image['url']
        except TypeError:
            images[0] = image['url']
            pass
    available_sizes = sorted(images)
    for size in available_sizes:
        if size >= preferred_size:
            return images[size]
    return images[available_sizes[-1]] if len(available_sizes) > 0 else ""


class MutableBool:
    def __init__(self, value: bool = False):
        self.__value = None
        self.set(bool(value))

    def set(self, value: bool):
        self.__value = bool(value)

    def __bool__(self):
        return self.__value

    def __int__(self):
        return 1 if self.__value else 0
