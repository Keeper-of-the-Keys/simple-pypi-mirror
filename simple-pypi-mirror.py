#!/usr/bin/env python3
#
# This file is intentionally indented with tabs to improve accessibility for visually impaired programmers
# As discussed here:
# https://www.reddit.com/r/javascript/comments/c8drjo/nobody_talks_about_the_real_reason_to_use_tabs/

# Return codes (default/undefined = 1):
FAILED_SYS_IMPORT		= 2
FAILED_IMPORTS			= 3
FAILED_ARGPARSE			= 4
FAILED_METADATA			= 5
FAILED_DIRECTORY		= 6

STATE_OK			= 0
STATE_MISSING			= 1
STATE_METADATA_MISSING		= 2

try:
	import sys
except Exception as e:
	print(str(e))
	exit(FAILED_SYS_IMPORT)

def print_error(message, exit_code = 1):
	'''Print error to stderr and exit unless exit_code is set to 0'''
	print(message, file=sys.stderr)
	if exit_code != 0:
		exit(exit_code)

try:
	import argparse
	import os
	import urllib.error
	import urllib.parse
	import urllib.request
	import shutil
	import hashlib
	import traceback
	from bs4 import BeautifulSoup
	from packaging.version import Version, parse, InvalidVersion
except Exception as e:
	print_error(f'Failed imports: {e}', FAILED_IMPORTS)


def get_package_metadata(package_name, index_url, include_prereleases = False):
	try:
		url = f'{index_url}{package_name}/'

		opener = urllib.request.build_opener()
		request = urllib.request.Request(url)
		results = opener.open(request).read().decode('utf-8')

		return read_package_metadata(results, package_name, include_prereleases)

	except Exception as e:
		print_error(f'get_package_metadata error: {e}', 0)
		raise e

def read_package_metadata(indexpage, package_name, include_prereleases = False):
	try:
		soup = BeautifulSoup(indexpage, 'html.parser')

		#unknown = []
		versions = {}
		for link in soup.find_all('a'):
			try:
				pkg = link.attrs
				pkg.update({'filename': link.get_text()})

				if link.get_text().endswith('.tar.gz'):
					version = link.get_text().removeprefix(package_name).split('-')[1].rstrip('.tar.gz')
				elif link.get_text().endswith('.whl'):
					version = link.get_text().removeprefix(package_name).split('-')[1]
					if pkg.get('data-core-metadata') is not None:
						# Strictly speaking this next check is not needed because the spec.
						if pkg['data-core-metadata'].find('=') > 0:
							pkg['meta_hash_algo'], pkg['meta_hash'] = pkg['data-core-metadata'].split('=')

				else:
					#print(f'WARNING: failed to parse: {pkg}')
					#unknown.append(pkg)
					continue

				try:
					if Version(version).is_prerelease and not include_prereleases:
						continue
				except InvalidVersion as e:
					continue

				if versions.get(version) is None:
					versions[version] = {}

				if pkg['href'].find('#') > 0:
					url, hash_def = pkg['href'].split('#')
					if hash_def.find('=') > 0:
						pkg['hash_algo'], pkg['hash'] = hash_def.split('=')

				versions[version][pkg['filename']] = pkg

			except Exception as e:
				print_error(f'read_package_metadata loop error: {e}\n{link}\n{pkg}', 0)
				raise e
		return versions

	except Exception as e:
		print_error(f'read_package_metadata error: {e}', 0)
		raise e

def download_file(url, destination):
	try:
		request = urllib.request.Request(url)

		with urllib.request.urlopen(request) as response:
			with open(destination, "wb") as f:
				shutil.copyfileobj(response, f)

		if url.find('#') > 0:
			url, hash_def = url.split('#')
			if hash_def.find('=') > 0:
				algo, hash = hash_def.split('=')

				if checksum(destination, getattr(hashlib, algo)) == hash:
					return True
				else:
					print_error(f'download_file: hash verification failed for {destination}', 0)
					return False
		return True

	except Exception as e:
		print_error(f'download_file error: {e}', 0)
		raise e

def checksum(filename, hash_factory=hashlib.sha256, chunk_num_blocks=128):
	''' Based on:
	https://stackoverflow.com/questions/1131220/get-the-md5-hash-of-big-files-in-python
	https://www.quickprogrammingtips.com/python/how-to-calculate-sha256-hash-of-a-file-in-python.html
	'''

	try:
		h = hash_factory()

		with open(filename,'rb') as f:
			while chunk := f.read(chunk_num_blocks*h.block_size):
				h.update(chunk)

		return h.hexdigest()

	except Exception as e:
		print_error(f'checksum error: {e}', 0)
		raise e

def download_package(args):
	'''
	This function needs to be split into smaller functions, was the main loop before addiung support for requirements.txt
	'''

	try:
		package_name = args.package_name
		requested_version = None

		if package_name.find('=') > 0:
			package_name, requested_version = package_name.split('=')[:2]

		versions = get_package_metadata(package_name, args.index)

		if len(versions) > 0:
			newest_version = sorted(versions.keys(), reverse=True, key=Version)[0]
		else:
			error_message = f'[{package_name}] Empty repository in remote index'
			if args.ignore_errors is True:
				print_error(error_message, 0)
				raise Exception(error_message)
			else:
				print_error(error_message, 1)


		if requested_version is None:
			requested_version = newest_version

		print(f'Processing package {package_name} version {requested_version}')

		# create/check folder
		path = f'{args.local_path}{package_name}'
		local_versions = {}

		if not os.path.isdir(path):
			try:
				os.makedirs(path)
			except Exception as e:
				error_message = f'[{package_name}]Failed to create directory {path} error: {e}'
				if args.ignore_errors is True:
					print_error(error_message, 0)
					raise Exception(error_message)
				else:
					print_error(error_message, FAILED_DIRECTORY)

		if not os.access(path, os.W_OK):
			error_message = f'[{package_name}]Local path {path} not writable'
			if args.ignore_errors is True:
				print_error(error_message, 0)
				raise Exception(error_message)
			else:
				print_error(error_message, FAILED_DIRECTORY)

		path_index = f'{path}/index.html'
		if os.path.isfile(path_index):
			with open(path_index, 'r') as f:
				local_versions = read_package_metadata(f.read(), package_name, True)

		for version, local_files in local_versions.items():
			for filename, local_file in local_files.items():
				if local_file.get('hash') is not None and versions[version][filename].get('hash') is not None:
					if local_file['hash'] == versions[version][filename]['hash']:
						if os.path.isfile(f'{path}/{filename}'):
							if local_file['hash'] == checksum(f'{path}/{filename}', getattr(hashlib, local_file['hash_algo'])):
								if filename.endswith('.whl'):
									if os.path.isfile(f'{path}/{filename}.metadata'):
										if versions[version][filename]['meta_hash'] == checksum(f'{path}/{filename}.metadata', getattr(hashlib, local_file['meta_hash_algo'])):
											versions[version][filename]['local_state'] = STATE_OK
											continue

									versions[version][filename]['local_state'] = STATE_METADATA_MISSING
									continue

								versions[version][filename]['local_state'] = STATE_OK
								continue

					# mark for redownload
					versions[version][filename]['local_state'] = STATE_MISSING
				elif versions[version][filename].get('hash') is not None:
					# compare local file hash and if ok add to  metadata (set changed flag)
					if os.path.isfile(f'{path}/{filename}'):
						if versions[version][filename]['hash'] == checksum(f'{path}/{filename}', getattr(hashlib, versions[version][filename]['hash_algo'])):
							if filename.endswith('.whl'):
								if os.path.isfile(f'{path}/{filename}.metadata'):
									if versions[version][filename]['meta_hash'] == checksum(f'{path}/{filename}.metadata', getattr(hashlib, local_file['meta_hash_algo'])):
										versions[version][filename]['local_state'] = STATE_OK
										local_versions[version][filename]['hash_algo'] = versions[version][filename]['hash_algo']
										local_versions[version][filename]['hash'] = versions[version][filename]['hash']
										continue

								versions[version][filename]['local_state'] = STATE_METADATA_MISSING
								continue

							versions[version][filename]['local_state'] = STATE_OK
							local_versions[version][filename]['hash_algo'] = versions[version][filename]['hash_algo']
							local_versions[version][filename]['hash'] = versions[version][filename]['hash']
							continue


					versions[version][filename]['local_state'] = STATE_MISSING
				else:
					# compare local hash to verify integrity?
					# log message that no comparison possible & mark for re-download?
					# Do nothing is effectively STATE_MISSING
					pass

		# Check for local files that were not included in the local index for whatever reason (process interrupted after download before index creation for instance)
		# Only files for which the parent index has a hash can be verified.
		for (dirpath, dirnames, filenames) in os.walk(path):
			break

		for filename in filenames:
			if filename.endswith('.tar.gz'):
				version = filename.removeprefix(package_name).split('-')[1].rstrip('.tar.gz')
			elif filename.endswith('.whl'):
				version = filename.removeprefix(package_name).split('-')[1]
			else:
				continue

			if versions[version][filename].get('local_state') is not None:
				continue

			if versions[version][filename].get('hash') is not None:
				if versions[version][filename]['hash'] == checksum(f'{path}/{filename}', getattr(hashlib, versions[version][filename]['hash_algo'])):
					versions[version][filename]['local_state'] = STATE_OK
					if local_versions.get(version) is None:
						local_versions[version] = {}
					local_versions[version][filename] = versions[version][filename]

		# check if already downloaded for each if not download
		if versions.get(requested_version) is None:
			error_message = f'[{package_name}] Version {requested_version} not found in remote index'
			if args.ignore_errors is True:
				print_error(error_message, 0)
				raise Exception(error_message)
			else:
				print_error(error_message, 1)

		for filename, pkg in versions[requested_version].items():
			local_filename = f'{args.local_path}{package_name}/{filename}'


			# check metadata mark
			if pkg.get('local_state') is not None:
				if pkg['local_state'] == STATE_OK:
					print(f'[{package_name}] STATE_OK Skipping')
					continue
				elif pkg['local_state'] == STATE_METADATA_MISSING:
					if pkg['href'].find('#') > 0:
						uri, hash = pkg['href'].split('#')
					else:
						uri = pkg['href']

					if download_file(f'{uri}.metadata', f'{local_filename}.metadata'):
						print(f'[{package_name}] Retrieved metadata for {filename}')
						continue
					else:
						print_error(f'[{package_name}] FAILED to retrieve metadata for {filename}', 0)
						continue


			if args.binary_only == True and filename.endswith('.tar.gz'):
				continue

			if args.source_only == True and filename.endswith('.whl'):
				continue

			if download_file(pkg['href'], local_filename):
				if local_filename.endswith('.whl'):
					if pkg['href'].find('#') > 0:
						uri, hash = pkg['href'].split('#')
					else:
						uri = pkg['href']

					if not download_file(f'{uri}.metadata', f'{local_filename}.metadata'):
						print_error(f'[{package_name}] FAILED to retrieve metadata for {filename}', 0)

				if local_versions.get(requested_version) is None:
					local_versions[requested_version] = {}
				local_versions[requested_version][filename] = pkg

		# (over)write index.html
		write_package_index(local_versions, args, package_name)

	except Exception as e:
		print_error(traceback.format_exc(), 0)
		print_error(f'download_package() error: {e}', 0)
		raise e

def write_package_index(metadata, args, package_name):
	index_path = f'{args.local_path}{package_name}/index.html'

	with open(index_path, 'w') as f:
	#write header
		f.write(f'''
<html>
	<head>
		<meta name="pypi:repository-version" content="1.3">
		<title>Links for {package_name}</title>
	</head>
	<body>
		<h1>Links for {package_name}</h1>
''')

		for version, filenames in metadata.items():
			for filename, pkg in filenames.items():
				href = f'href="{filename}#{pkg['hash_algo']}={pkg['hash']}"' if pkg.get('hash_algo') is not None else f'href="{filename}"'
				data_requires_python = f'data-requires-python="{pkg['data-requires-python']}"' if pkg.get('data-requires-python') is not None else ''
				data_dist_info_metadata = f'data-dist-info-metadata="{pkg['data-dist-info-metadata']}"' if pkg.get('data-dist-info-metadata') is not None else ''
				data_core_metadata = f'data-core-metadata="{pkg['data-core-metadata']}"' if pkg.get('data-core-metadata') is not None else ''

				f.write(f'\t\t<a {href} {data_requires_python} {data_dist_info_metadata} {data_core_metadata}>{filename}</a><br />\n')

#				if filename.endswith('tar.gz')
#					if pkg.get('hash_algo') is not None:
#						f.write(f'\t\t<a href="{filename}#{pkg['hash_algo']}={pkg['hash']}">{filename}</a><br />\n')
#					else:
#						f.write(f'\t\t<a href="{filename}">{filename}</a><br />\n')
#
#				if filename.endswith('.whl'):
#					if pkg.get('hash_algo') is not None:
#						f.write(f'\t\t<a href="{filename}#{pkg['hash_algo']}={pkg['hash']}" data-requires-python="{pkg['data-requires-python']}" data-dist-info-metadata="{pkg['data-dist-info-metadata']}" data-core-metadata="{pkg['data-core-metadata']}">{filename}</a><br />\n')
#					else:
#						f.write(f'\t\t<a href="{filename}" data-requires-python="{pkg['data-requires-python']}" data-dist-info-metadata="{pkg['data-dist-info-metadata']}" data-core-metadata="{pkg['data-core-metadata']}">{filename}</a><br />\n')
	#write footer
		f.write(f'''
	</body>
</html>
''')

def write_main_index(index_path):
	for (dirpath, dirnames, filenames) in os.walk(index_path):
		break

	with open(f'{index_path}index.html', 'w') as f:
		f.write('''
<html>
	<head>
		<meta name="pypi:repository-version" content="1.3">
		<title>Simple index</title>
	</head>
	<body>
''')
		for dirname in dirnames:
			f.write(f'\t\t<a href="{dirname}">{dirname}</a><br />')
		f.write('''
	</body>
</html>
''')

'''
class RepositoryTree()

Contains:
1. All *requested* packages with their remote and local states
2. All *local* packages with their state [[local state should also only read requested packages and their dependencies, since if a mirror is big the datastructure may get unnecissarily large]]

Package states are only verified to prevent download, so if a package is not "hit" it is not verified.

The "state" of a package is which versions are available from the source remote/local, which version(s) are requested and in the case verification happened the verification state

Tree
	Package
		Versions = {}
			State
		UnsortableVersions = {}
			State
		RequestedVersions = []

'''
def requirements_loop(args):
	try:
		print(f'Processing requirements file: {args.package_name}')
		if os.path.isfile(args.package_name):
			with open(args.package_name, 'r') as f:
				packages = [line.lstrip(' -').rstrip('\n') for line in f.readlines() if line.find(':') == -1 and not line.startswith('#')]

		local_args = args
		errors = []
		successful_packages = []
		for package in sorted(set(packages)):
			try:
				local_args.package_name = package
				download_package(local_args)
				successful_packages.append(package)
			except Exception as e:
				print_error(f'requirements_loop() loop error: {e} with {package}', 0)
				errors.append(f'[{package}]: {e}')

		if len(errors) > 0:
			print(f'{len(errors)} packages had errors.\nThe following packages had errors:')
			for error in errors:
				print(error)

		if len(successful_packages) > 0:
			print(f'{len(successful_packages)} packages cached successfully:')
			for pkg in successful_packages:
				print(pkg)

	except Exception as e:
		print_error(f'requirements_loop() error: {e}', 0)
		raise e

if __name__ == "__main__":
	try:
		parser = argparse.ArgumentParser(__file__)

		parser.add_argument(	'--index',
					dest 	= 'index',
					help 	= 'Address of PyPI simple API to use',
					metavar = 'https://pypi.org/simple/',
					default = 'https://pypi.org/simple/',
					)

		parser.add_argument(	'--local-folder',
					dest 	= 'local_path',
					help 	= 'Folder where the simple index is stored',
					metavar = '/var/www/pypi/simple/',
					default = '/tmp/simple/',
					)

		parser.add_argument(	'--ignore-errors',
					dest 	= 'ignore_errors',
					help 	= 'Continue to the next package when there is an error',
					action	= 'store_true',
					)

		parser.add_argument(	'--include-prereleases',
					dest 	= 'include_beta',
					help 	= 'Allow prerelease software to be downloaded when no version is specified.',
					action	= 'store_true',
					)

		download = parser.add_mutually_exclusive_group()

		download.add_argument(	'--binary-only',
					dest 	= 'binary_only',
					help 	= 'Only download binary wheel files (.whl)',
					action	= 'store_true',
					)

		download.add_argument(	'--source-only',
					dest 	= 'source_only',
					help 	= 'Only download source archives (.tar.gz)',
					action	= 'store_true',
					)

		parser.add_argument(	'package_name',
					help 	= 'Package name and optionally version or path to requirements.txt',
					metavar = '(somepackage|somepackage=1.10.0|req.txt)',
					)

		args = parser.parse_args()
	except Exception as e:
		print_error('argparse failure: ' + str(e), FAILED_ARGPARSE)

	try:
		if not args.local_path.endswith('/'):
			args.local_path = f'{args.local_path}/'

		if os.path.isfile(args.package_name):
			requirements_loop(args)
		else:
			download_package(args)

		write_main_index(args.local_path)


	except Exception as e:
		print_error(f'generic error: {e}')
	exit(0)


