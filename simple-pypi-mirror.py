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
class SimplePyPIMirrorTree:
	def __init__(self, args):
		self.tree = {}
		self.errors = []
		self.successful_packages = []
		self.args = args

	def add_request(self, package):
		try:
			if package.find('=') > 0:
				pkg_name, pkg_version = package.split('=')[:2]
			else:
				pkg_name = package
				pkg_version = None

			if self.tree.get(pkg_name) is None:
				self.tree[pkg_name] = SimplePyPIMirrorDistribution(package, self.args.local_path, self.args.index, self, self.args.include_beta)
			else:
				self.tree[pkg_name].get_version(pkg_version)

			self.successful_packages.append(package)
		except Exception as e:
			print_error(f'requirements_loop() loop error: {e} with {package}', 0)
			self.errors.append(f'[{package}]: {e}')

	def print_summary(self):
		if len(self.errors) > 0:
			print(f'{len(self.errors)} packages had errors.\nThe following packages had errors:')
			for error in self.errors:
				print(error)

		if len(self.successful_packages) > 0:
			print(f'{len(self.successful_packages)} packages cached successfully:')
			for pkg in self.successful_packages:
				print(pkg)


class SimplePyPIMirrorDistribution:
	def __init__(self, name, local_path, remote_index, parent, include_prereleases = False):
		self.parent = parent
		self.name = name
		self.newest_version = None
		self.requested_version = None

		if name.find('=') > 0:
			self.name, self.requested_version = name.split('=')[:2]

		self.local_path = local_path
		self.path = f'{self.local_path}{self.name}'

		self.local_versions = {}
		self.remote_versions = self.get_metadata(remote_index)

		if len(self.remote_versions) > 0:
			sorted_version_list = sorted([x for x in self.remote_versions.keys() if Version(x)], reverse=True, key=Version)
			try:
				self.newest_version = next(v for v in sorted_version_list if Version(v).is_prerelease == include_prereleases)
			except StopIteration:
				# The distribution can be setup without a known newest version, 
				# only at the download stage does this become an issue if no requested and no newest.
				pass
		else:
			raise Exception(f'[{self.name}] Empty repository in remote index')

		if self.requested_version is None and self.newest_version is not None:
			self.requested_version = self.newest_version

		self.read_local_metadata()
		self.verify_local_metadata()
		self.scan_local_files()

		if self.requested_version is not None:
			try:
				self.download_version()
			except Exception as e:
				print_error(e, 0)

	def read_local_metadata(self):
		if not os.path.isdir(self.path):
			try:
				os.makedirs(self.path)
			except Exception as e:
				raise Exception(f'[{self.name}]Failed to create directory {self.path} error: {e}')

		if not os.access(self.path, os.W_OK):
			raise Exception(f'[{self.name}]Local path {self.path} not writable')

		path_index = f'{self.path}/index.html'
		if os.path.isfile(path_index):
			with open(path_index, 'r') as f:
				self.local_versions = self.read_metadata(f.read())

	def verify_local_metadata(self):
		for version, local_files in self.local_versions.items():
			for filename, local_file in local_files.items():
				if local_file.get('hash') is not None and self.remote_versions[version][filename].get('hash') is not None:
					if local_file['hash'] == self.remote_versions[version][filename]['hash']:
						if os.path.isfile(f'{self.path}/{filename}'):
							if local_file['hash'] == checksum(f'{self.path}/{filename}', getattr(hashlib, local_file['hash_algo'])):
								if filename.endswith('.whl'):
									if os.path.isfile(f'{self.path}/{filename}.metadata'):
										if self.remote_versions[version][filename]['meta_hash'] == checksum(f'{self.path}/{filename}.metadata', getattr(hashlib, local_file['meta_hash_algo'])):
											self.remote_versions[version][filename]['local_state'] = STATE_OK
											continue

									self.remote_versions[version][filename]['local_state'] = STATE_METADATA_MISSING
									continue

								self.remote_versions[version][filename]['local_state'] = STATE_OK
								continue

					# mark for redownload
					self.remote_versions[version][filename]['local_state'] = STATE_MISSING
				elif self.remote_versions[version][filename].get('hash') is not None:
					# compare local file hash and if ok add to  metadata (set changed flag)
					if os.path.isfile(f'{self.path}/{filename}'):
						if self.remote_versions[version][filename]['hash'] == checksum(f'{self.path}/{filename}', getattr(hashlib, self.remote_versions[version][filename]['hash_algo'])):
							if filename.endswith('.whl'):
								if os.path.isfile(f'{self.path}/{filename}.metadata'):
									if self.remote_versions[version][filename]['meta_hash'] == checksum(f'{self.path}/{filename}.metadata', getattr(hashlib, local_file['meta_hash_algo'])):
										self.remote_versions[version][filename]['local_state'] = STATE_OK
										self.local_versions[version][filename]['hash_algo'] = self.remote_versions[version][filename]['hash_algo']
										self.local_versions[version][filename]['hash'] = self.remote_versions[version][filename]['hash']
										continue

								self.remote_versions[version][filename]['local_state'] = STATE_METADATA_MISSING
								continue

							self.remote_versions[version][filename]['local_state'] = STATE_OK
							self.local_versions[version][filename]['hash_algo'] = self.remote_versions[version][filename]['hash_algo']
							self.local_versions[version][filename]['hash'] = self.remote_versions[version][filename]['hash']
							continue


					self.remote_versions[version][filename]['local_state'] = STATE_MISSING
				else:
					# compare local hash to verify integrity?
					# log message that no comparison possible & mark for re-download?
					# Do nothing is effectively STATE_MISSING
					pass

	def scan_local_files(self):
		# Check for local files that were not included in the local index for whatever reason (process interrupted after download before index creation for instance)
		# Only files for which the parent index has a hash can be verified.
		for (dirpath, dirnames, filenames) in os.walk(self.path):
			break

		for filename in filenames:
			if filename.endswith('.tar.gz'):
				version = filename.removeprefix(self.name).split('-')[1].rstrip('.tar.gz')
			elif filename.endswith('.whl'):
				version = filename.removeprefix(self.name).split('-')[1]
			else:
				continue

			if self.remote_versions[version][filename].get('local_state') is not None:
				continue

			if self.remote_versions[version][filename].get('hash') is not None:
				if self.remote_versions[version][filename]['hash'] == checksum(f'{self.path}/{filename}', getattr(hashlib, self.remote_versions[version][filename]['hash_algo'])):
					self.remote_versions[version][filename]['local_state'] = STATE_OK
					if self.local_versions.get(version) is None:
						self.local_versions[version] = {}
					self.local_versions[version][filename] = self.remote_versions[version][filename]


	def get_metadata(self, index_url):
		try:
			url = f'{index_url}{self.name}/'

			opener = urllib.request.build_opener()
			request = urllib.request.Request(url)
			results = opener.open(request).read().decode('utf-8')

			return self.read_metadata(results)

		except Exception as e:
			print_error(f'get_package_metadata error: {e}', 0)
			raise e

	def read_metadata(self, indexpage):
		try:
			soup = BeautifulSoup(indexpage, 'html.parser')

			versions = {}
			for link in soup.find_all('a'):
				try:
					pkg = link.attrs
					pkg.update({'filename': link.get_text()})

					if link.get_text().endswith('.tar.gz'):
						version = link.get_text().removeprefix(self.name).split('-')[1].rstrip('.tar.gz')
					elif link.get_text().endswith('.whl'):
						version = link.get_text().removeprefix(self.name).split('-')[1]
						if pkg.get('data-core-metadata') is not None:
							# Strictly speaking this next check is not needed because the spec.
							if pkg['data-core-metadata'].find('=') > 0:
								pkg['meta_hash_algo'], pkg['meta_hash'] = pkg['data-core-metadata'].split('=')

					else:
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

	def download_version(self):
		# check if already downloaded for each if not download
		print(f'[{self.name}] Starting download of version: {self.requested_version}')
		if self.remote_versions.get(self.requested_version) is None:
			raise Exception(f'[{self.name}] Version {self.requested_version} not found in remote index')

		for filename, pkg in self.remote_versions[self.requested_version].items():
			local_filename = f'{self.local_path}{self.name}/{filename}'


			# check metadata mark
			if pkg.get('local_state') is not None:
				if pkg['local_state'] == STATE_OK:
					print(f'[{self.name}] STATE_OK Skipping [{filename}]')
					continue
				elif pkg['local_state'] == STATE_METADATA_MISSING:
					if pkg['href'].find('#') > 0:
						uri, hash = pkg['href'].split('#')
					else:
						uri = pkg['href']

					if download_file(f'{uri}.metadata', f'{local_filename}.metadata'):
						print(f'[{self.name}] Retrieved metadata for {filename}')
						continue
					else:
						print_error(f'[{self.name}] FAILED to retrieve metadata for {filename}', 0)
						continue


			#if args.binary_only == True and filename.endswith('.tar.gz'):
			#	continue

			#if args.source_only == True and filename.endswith('.whl'):
			#	continue

			if download_file(pkg['href'], local_filename):
				if local_filename.endswith('.whl'):
					if pkg['href'].find('#') > 0:
						uri, hash = pkg['href'].split('#')
					else:
						uri = pkg['href']

					if not download_file(f'{uri}.metadata', f'{local_filename}.metadata'):
						print_error(f'[{self.name}] FAILED to retrieve metadata for {filename}', 0)

				if self.local_versions.get(self.requested_version) is None:
					self.local_versions[self.requested_version] = {}
				self.local_versions[self.requested_version][filename] = pkg

	def get_version(self, version):

		self.requested_version = version

		if self.requested_version is None and self.newest_version is not None:
			self.requested_version = self.newest_version

		self.download_version()

	def write_package_index(self):
		index_path = f'{self.local_path}{self.name}/index.html'

		with open(index_path, 'w') as f:
		#write header
			f.write(f'''
<html>
	<head>
		<meta name="pypi:repository-version" content="1.3">
		<title>Links for {self.name}</title>
	</head>
	<body>
		<h1>Links for {self.name}</h1>
''')

			for version, filenames in metadata.items():
				for filename, pkg in filenames.items():
					href = f'href="{filename}#{pkg['hash_algo']}={pkg['hash']}"' if pkg.get('hash_algo') is not None else f'href="{filename}"'
					data_requires_python = f'data-requires-python="{pkg['data-requires-python']}"' if pkg.get('data-requires-python') is not None else ''
					data_dist_info_metadata = f'data-dist-info-metadata="{pkg['data-dist-info-metadata']}"' if pkg.get('data-dist-info-metadata') is not None else ''
					data_core_metadata = f'data-core-metadata="{pkg['data-core-metadata']}"' if pkg.get('data-core-metadata') is not None else ''

					f.write(f'\t\t<a {href} {data_requires_python} {data_dist_info_metadata} {data_core_metadata}>{filename}</a><br />\n')

			f.write(f'''
	</body>
</html>
''')

def requirements_loop(args):
	try:
		print(f'Processing requirements file: {args.package_name}')
		if os.path.isfile(args.package_name):
			with open(args.package_name, 'r') as f:
				packages = [line.lstrip(' -').rstrip('\n') for line in f.readlines() if line.find(':') == -1 and not line.startswith('#')]

		tree = SimplePyPIMirrorTree(args)

		for package in sorted(set(packages)):
			tree.add_request(package)

		tree.print_summary()

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


