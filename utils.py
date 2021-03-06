import requests
import os
import json
import tempfile
import re
import pandas as pd
from collections import namedtuple

CACHE_NAME = os.path.join(tempfile.gettempdir(), 'openra_map_hash_names.json')
ROOT_URL = 'http://resource.openra.net/map/hash/{map_hash}'


def build_map_hash_to_name_mapping(hashes, force=False):
    if not os.path.isfile(CACHE_NAME) or force:
        results = build_cached_results(hashes)
        with open(CACHE_NAME, 'w') as outfile:
            json.dump(results, outfile, indent=2)

    with open(CACHE_NAME) as infile:
        return json.load(infile)


def build_cached_results(hashes):
    result = {}
    for h in hashes:
        map_name = fetch_map_name(h)
        result[h] = map_name
    return result


def fetch_map_name(hash):
    url = ROOT_URL.format(map_hash=hash)
    response = requests.get(url)
    try:
        response.raise_for_status()
    except requests.HTTPError:
        return None

    payload = response.json()
    return payload[0]['title']



OpenGLDescriptor = namedtuple('OpenGLDescriptor', [
    'version', 'driver', 'driver_version'])


class GLParser(object):

    opengl_version_re = re.compile(
        r'\d+\.\d+(\.\d+)?')
    compat_version_re = re.compile(
        r'\d+\.\d+\.\d+\.\d+')
    mesa_version_re = re.compile(
        r'\d+\.\d+\.\d+')
    intel_version_re = re.compile(
        r'INTEL-(?P<version>\d+\.\d+\.\d+)')
    nvidia_version_re = re.compile(
        r'NVIDIA (?P<version>\d{3}\.\d+)')
    build_version_re = re.compile(
        r'Build (?P<version>\d+\.\d+\.\d+\.\d+)')

    def parse(self, s):
        if isinstance(s, int):
            return OpenGLDescriptor(
                version='{}.0.0'.format(s),
                driver=None,
                driver_version=None)
        elif isinstance(s, float):
            return OpenGLDescriptor(
                version=str(s),
                driver=None,
                driver_version=None)
        elif 'Compatibility Profile Context' in s:
            return self.parse_compatability_profile_context(s)
        elif 'Mesa' in s:
            return self.parse_mesa(s)
        elif 'NVIDIA' in s:
            return self.parse_nvidia(s)
        elif 'INTEL' in s:
            return self.parse_intel(s)
        elif 'Build' in s:
            return self.parse_build_version(s)
        else:
            gl_version = self._opengl_version(s)
            if gl_version:
                return OpenGLDescriptor(
                    version=gl_version,
                    driver='generic',
                    driver_version=None)
            else:
                raise NotImplementedError('Unimplemented for {}'.format(s))

    def parse_build_version(self, s):
        match = self.build_version_re.search(s)
        if match:
            driver_version = match.group('version')
        else:
            driver_version = None
        return OpenGLDescriptor(
            version=self._opengl_version(s),
            driver='build',
            driver_version=driver_version)

    def parse_nvidia(self, s):
        match = self.nvidia_version_re.search(s)
        if match:
            nvidia_version = match.group('version')
        else:
            nvidia_version = None
        return OpenGLDescriptor(
            version=self._opengl_version(s),
            driver='nvidia',
            driver_version=nvidia_version)

    def parse_intel(self, s):
        match = self.intel_version_re.search(s)
        if match:
            intel_version = match.group('version')
        else:
            intel_version = None
        return OpenGLDescriptor(
            version=self._opengl_version(s),
            driver='intel',
            driver_version=intel_version)

    def parse_mesa(self, s):
        match = self.mesa_version_re.search(s)
        if match:
            driver_version = match.group(0)
        else:
            driver_version = None

        return OpenGLDescriptor(
            version=self._opengl_version(s),
            driver='mesa',
            driver_version=driver_version)

    def parse_compatability_profile_context(self, s):
        match = self.compat_version_re.search(s)
        if match:
            driver_version = match.group(0)
        else:
            driver_version = None

        return OpenGLDescriptor(
            version=self._opengl_version(s),
            driver='compat',
            driver_version=driver_version)

    def _opengl_version(self, s):
        match = self.opengl_version_re.search(s)
        if match:
            return match.group(0)

Runtime = namedtuple('Runtime', ['provider', 'version'])

def parse_gl_versions(gl_version_strings):
    parser = GLParser()
    for i, entry in enumerate(gl_version_strings):
        yield parser.parse(entry)


def parse_runtime(runtime):
    if runtime is None:
        return None

    if 'Mono' in runtime:
        return parse_mono_runtime(runtime)
    elif '.NET' in runtime:
        return parse_dotnet_runtime(runtime)
    else:
        raise ValueError('Invalid runtime value: {}'.format(runtime))


def parse_mono_runtime(value):
    version = value.split()[1]
    return Runtime(
        provider='mono',
        version=version)


def parse_dotnet_runtime(value):
    version = value.split()[2]
    return Runtime(
        provider='.net',
        version=version)


def timely_map_breakdown(df, sample_time):
    sample_time = sample_time.lower()
    resample_remapping = {
        'weekly': 'W',
        'daily': 'D',
        'hourly': 'H',
        'monthly': 'M',
    }

    if sample_time not in resample_remapping:
        raise KeyError('Resample value must be one of `{}`'.format(
            tuple(resample_remapping.keys())))

    pandas_resample = resample_remapping[sample_time]
    counts = df.groupby('map_name').resample(pandas_resample).map.count()
    max_values = {}

    for idx, played_count in counts.iteritems():
        map_name, timestamp = idx
        if timestamp in max_values:
            existing_count, existing_name = max_values[timestamp]
            if played_count > existing_count:
                max_values[timestamp] = (played_count, map_name)
        else:
            max_values[timestamp] = (played_count, map_name)

    times = sorted(list(max_values.keys()))

    max_map = pd.Series(
        data=[max_values[t][1] for t in times],
        index=times)
    categories = pd.Categorical(max_map)
    return pd.DataFrame(
        data={'map': categories, 'map_index': categories.codes},
        index=times)
