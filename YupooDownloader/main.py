# Attempt to import Windows-only modules at module load time.  These modules
# are only available on Windows and will raise ImportError on other
# platforms; in that case fall back to None.  The variables `winshell`
# and `Dispatch` are later used in the YupooDownloader helper.
try:
    import winshell  # noqa: F401  (unused, kept for compatibility)
except ImportError:
    winshell = None  # type: ignore
try:
    from win32com.client import Dispatch  # type: ignore
except ImportError:
    Dispatch = None  # type: ignore

if __name__ == "__main__":
	import app
else:
	import os
	os.environ['PYTHONASYNCIODEBUG'] = '1'

	import logging
	DEFAULT_PATH = os.path.dirname(__file__)
	logger = logging.getLogger()
	logger.setLevel(logging.INFO)
	formatter = logging.Formatter(fmt='%(asctime)s - %(levelname)s - %(message)s', datefmt='%d/%m/%Y %H:%M:%S')

	fh = logging.FileHandler(f"{DEFAULT_PATH}/info.log",mode="a",encoding="utf-8")
	fh.setFormatter(formatter)
	logger.addHandler(fh)

	logger.info("start v1.4.2")

    # The Windows-specific modules are imported at module load time at the top
    # of this file; see above for details.
	import asyncio
	import re
	import aiohttp
	import aiofiles
	from bs4 import BeautifulSoup
	import lxml
	import regex
	from time import perf_counter
	from alive_progress import alive_bar
	from rich.console import Console
	import traceback
	import piexif
	from PIL import ImageFile
	ImageFile.LOAD_TRUNCATED_IMAGES = True
	from PIL import Image as Image
	from io import BytesIO
	from copy import deepcopy

	import ssl
	import certifi
	sslcontext = ssl.create_default_context(cafile=certifi.where())

    # -------------------------------------------------------------------------
    # The helper function `create_shortcut` is now defined as a method of the
    # YupooDownloader class.  It will be injected later in the class
    # definition to avoid indentation issues at the module level.

	import json
	from urllib.parse import urlparse, parse_qs  # import for parsing search query
	with open(DEFAULT_PATH + '/config.json', 'r') as f:
		config = json.load(f)
	OUTPUT_PATH = config['path_to_save']
	logger.info(OUTPUT_PATH)

	class YupooDownloader():
		def __init__(self, all_albums, urls = None, cover=False):
			self.start_time_class = perf_counter()
			self.now = lambda: round(perf_counter()-self.start_time, 2)
			self.console = Console(color_system="auto")
			self.all_albums = all_albums
			self.urls = urls
			logger.info(str(self.urls))
			self.cover = cover
			self.albums = {}
			self.normpath = lambda path: os.path.normpath(path)
			# Initialize a list to store URLs (albums or images) that fail after several attempts
			self.failed_urls = []


			# HTTP request headers (cookie and user-agent) must be defined on the instance.
			self.headers = {
				'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1',
				'referer': "https://1998shoe.x.yupoo.com/",
				'Cookie': 'language=pt; Hm_lvt_28019b8719a5fff5b26dfb4079a63dab=1765290370; HMACCOUNT=2445C44D9A657488; _c_WBKFRo=0Lk2D1bJm7SEOnRwmTMyU663np4Bxl1otrNRrTRJ; _nb_ioWEgULi=; indexlockcodeRemember=HJH001077; indexlockcode=HJH001077; version=7.11.14; _gid=GA1.2.1907859279.1765290766; searchPrioritize=album; _ga_3R06MM98Q4=GS2.1.s1765293430$o2$g0$t1765293430$j60$l0$h0; _ga_P5QMXEZ5BQ=GS2.1.s1765293430$o2$g0$t1765293430$j60$l0$h0; _ga=GA1.1.471232977.1762531460; _ga_XMN82VEYLV=GS2.1.s1765322005$o10$g1$t1765323221$j44$l0$h0; Hm_lpvt_28019b8719a5fff5b26dfb4079a63dab=1765323222'
			}

			# Timeout and retry control parameters for HTTP connections
			self.timeout_connect = [30]
			self.connect_control = [0]
			self.connect_errors = [0]

			self.timeout_read = [30]
			self.read_control = [0]
			self.read_errors = [0]

			# Limit concurrent requests to avoid server blocking; allow up to 8 concurrent connections
			self.sem = asyncio.Semaphore(8)
			# Store initial timeout settings for comparison and dynamic adjustment
			self.timeout = aiohttp.ClientTimeout(connect=self.timeout_connect[0], sock_read=self.timeout_read[0])
			self.oldtimeout = [self.timeout.connect, self.timeout.sock_read]

		class FatalException(Exception):
			pass

		# ---------------------------------------------------------------------
		# Shortcut/Symlink helper
		#
		# This helper method encapsulates the logic for creating a Windows
		# shortcut (.lnk) or a Unix-style symbolic link pointing to an album
		# directory.  On Windows platforms the method leverages the COM
		# interface provided by `WScript.Shell` when available.  On other
		# platforms it falls back to creating a symbolic link via `os.symlink`.
		# Errors are logged via the module-level logger; they do not abort
		# downloads.
		def create_shortcut(self, save_path: str, album: str, target: str, work_dir: str) -> None:
			try:
				# Import sys locally to determine the platform.  Dispatch is imported
				# conditionally at module load time.
				import sys
				if sys.platform.startswith("win") and Dispatch is not None:
					# Ensure the destination directory exists
					if not os.path.exists(save_path):
						os.makedirs(save_path, exist_ok=True)
					# Create a Windows shortcut (.lnk) via COM
					shell = Dispatch('WScript.Shell')
					shortcut_path = os.path.join(save_path, f"{album}.lnk")
					shortcut = shell.CreateShortCut(shortcut_path)
					shortcut.Targetpath = target
					shortcut.WorkingDirectory = work_dir
					shortcut.save()
				else:
					# On non-Windows platforms, fall back to a symbolic link
					if not os.path.exists(save_path):
						os.makedirs(save_path, exist_ok=True)
					link_path = os.path.join(save_path, album)
					# Remove any existing file/link first
					if os.path.exists(link_path) or os.path.islink(link_path):
						try:
							os.unlink(link_path)
						except Exception:
							pass
					os.symlink(target, link_path)
			except Exception as e:
				logger.info(f"Failed to create shortcut/symlink for '{album}': {e}")

		async def main(self):
			session = aiohttp.ClientSession()
			async with session as self.session:
				if self.all_albums:
					self.pages = await self.get_pages()
					#getting albums from pages resp
					self.tasks = []
					for page in self.pages:
						self.tasks.append(asyncio.ensure_future(self.async_req(page, self.get_albums)))
					logger.info(f"[all_albums] getting albums from pages resp: {len(self.tasks)}")
					self.console.print("\n[#6149ab]Pegando álbuns das páginas[/]")
					self.start_time = perf_counter()
					with alive_bar(len(self.tasks), length=35, bar="squares", spinner="classic", elapsed="em {elapsed}") as self.bar:
						await self._(self.tasks, self.get_albums)
					logger.info(self.now())

					#getting images from albums resp
					self.tasks = []
					for catalog in self.albums:
							for album in self.albums[catalog]:
								self.tasks.append(asyncio.ensure_future(self.async_req(self.albums[catalog][album]['album_link'], self.get_album)))
					logger.info(f"[all_albums] getting images from albums resp: {len(self.tasks)}")
					self.console.print("\n[#6149ab]Pegando as imagens dos álbuns[/]")
					with alive_bar(len(self.tasks), length=35, bar="squares", spinner="classic", elapsed="em {elapsed}") as self.bar:
						self.start_time = perf_counter()
						if len(self.tasks) > 0:
							await self._(self.tasks, self.get_album)
					logger.info(self.now())

				else:
					# In options 3 and 4, treat each provided URL as a direct album link.
					# Allow the user to input multiple album links (8 or more).
					# The application will parse each URL, normalize it, and schedule a download task for each distinct album.
					self.tasks = []
					urls = []
					# Normalize provided URLs and avoid duplicates
					for url in self.urls:
						# Remove query parameters except for uid; unify spacing
						rx = re.findall(r'(?<=\?)(.*?)(?=$)', url)
						rx = rx[0] if len(rx) > 0 else None
						new_url = url
						if rx is not None:
							new_url = ''
							for i, st in enumerate(url.split(rx)):
								if st.strip() == '':
									continue
								if i != 0:
									new_url += f' {st.strip()}'
								else:
									new_url += st.strip()
							# Ensure uid parameter present
							if 'uid=' not in new_url:
								if '?' in new_url:
									if not new_url.endswith('&') and not new_url.endswith('?'):
										new_url += '&'
									new_url += 'uid=1'
								else:
									new_url += '?uid=1'
						# Append to list if not already present
						if new_url not in urls:
							urls.append(new_url)

					# Schedule a task for each album link
					for album_url in urls:
						# Avoid reprocessing albums already in self.albums
						existing = await self.find_key(self.albums, album_url)
						if existing is None:
							self.tasks.append(asyncio.ensure_future(self.async_req(album_url, self.get_album)))

					# Fetch album pages and images
					self.start_time = perf_counter()
					if len(self.tasks) > 0:
						logger.info(f"[all_albums == False] getting images from albums resp: {len(self.tasks)}")
						self.console.print("\n[#6149ab]Pegando as imagens dos álbuns[/]")
						with alive_bar(len(self.tasks), length=35, bar="squares", spinner="classic", elapsed="em {elapsed}") as self.bar:
							await self._(self.tasks, self.get_album)
					logger.info(self.now())
				
				#downloading imgs in albums
				self.tasks=[]	
				self.start_time = perf_counter()
				if self.all_albums:
					for catalog in self.albums:
							for album in self.albums[catalog]:
								name_catalog = catalog
								if 'imgs' in self.albums[catalog][album]:
									for img in self.albums[catalog][album]['imgs']:
										img_link = img
										if img_link == "video": continue
										img_title = re.findall(r'/((?:(?!/).)*)$', img_link)[0].split('.')[0] #/((?:(?!/).)*)$
										path = f"{OUTPUT_PATH}/fotos_yupoo/{name_catalog}/albuns/{album}/{img_title}.jpeg"
										if os.path.exists(path):
											without_category_path = f"{OUTPUT_PATH}/fotos_yupoo/{name_catalog}/categorias/sem categoria/{album}.lnk"
											if os.path.exists(without_category_path):
												os.unlink(without_category_path)
												if len(os.listdir(f"{OUTPUT_PATH}/fotos_yupoo/{name_catalog}/categorias/sem categoria/")) == 0:
													os.rmdir(f"{OUTPUT_PATH}/fotos_yupoo/{name_catalog}/categorias/sem categoria/")
												album_path = self.albums[catalog][album]
												if 'category_title' in album_path:
													save_path = self.normpath(f"{OUTPUT_PATH}/fotos_yupoo/{name_catalog}/categorias/{album_path['category_title']}/")
													target = self.normpath(f"{OUTPUT_PATH}/fotos_yupoo/{name_catalog}/albuns/{album}")  # The shortcut target file or folder
													work_dir = self.normpath(f"{OUTPUT_PATH}/fotos_yupoo/{name_catalog}/albuns/")  # The parent folder of your file

													
											continue
										self.tasks.append(asyncio.ensure_future(self.async_req(img_link, self.get_imgs)))
					if len(self.tasks) > 0:
						self.console.print('\n[#6149ab]Baixando as imagens dos álbuns[#6149ab]')
						with alive_bar(len(self.tasks), length=35, bar="squares", spinner="classic", elapsed="em {elapsed}") as self.bar:
							logger.info(f"[all_albums] downloading imgs in albums: {len(self.tasks)}")
							await self._(self.tasks, self.get_imgs)
				else:
						for catalog in self.albums:
							for album in self.albums[catalog]:
								name_catalog = catalog
								if 'imgs' in self.albums[catalog][album]:
									for img in self.albums[catalog][album]['imgs']:
										if img == "video":
											continue
										img_link = img
										if img_link == "video": continue
										img_title = re.findall(r'/((?:(?!/).)*)$', img_link)[0].split('.')[0] #/((?:(?!/).)*)$
										path = f"{OUTPUT_PATH}/fotos_yupoo/{name_catalog}/albuns/{album}/{img_title}.jpeg"
										if os.path.exists(path):
											without_category_path = f"{OUTPUT_PATH}/fotos_yupoo/{name_catalog}/categorias/sem categoria/{album}.lnk"
											if os.path.exists(without_category_path):
												os.unlink(without_category_path)
												if len(os.listdir(f"{OUTPUT_PATH}/fotos_yupoo/{name_catalog}/categorias/sem categoria/")) == 0:
													os.rmdir(f"{OUTPUT_PATH}/fotos_yupoo/{name_catalog}/categorias/sem categoria/")
												album_path = self.albums[catalog][album]
												if 'category_title' in album_path:
													save_path = self.normpath(f"{OUTPUT_PATH}/fotos_yupoo/{name_catalog}/categorias/{album_path['category_title']}/")
													target = self.normpath(f"{OUTPUT_PATH}/fotos_yupoo/{name_catalog}/albuns/{album}")  # The shortcut target file or folder
													work_dir = self.normpath(f"{OUTPUT_PATH}/fotos_yupoo/{name_catalog}/albuns/")  # The parent folder of your file

													
											continue
										self.tasks.append(asyncio.ensure_future(self.async_req(img_link, self.get_imgs)))
						self.start_time = perf_counter()
						if len(self.tasks) > 0:
							logger.info(f"[all_albums == False] downloading imgs in albums: {len(self.tasks)}")
							self.console.print('\n[#6149ab]Baixando as imagens dos álbuns[#6149ab]')
							with alive_bar(len(self.tasks), length=35, bar="squares", spinner="classic", elapsed="em {elapsed}") as self.bar:
								await self._(self.tasks, self.get_imgs)
						logger.info(self.now())
								
				logger.info(f"finish: {round(perf_counter() - self.start_time_class, 2)}")
				# Report any URLs that failed after exceeding retry attempts
				if self.failed_urls:
					self.console.print("\n[b #c7383f]Não foi possível baixar alguns links após várias tentativas:[/]")
					for failed in self.failed_urls:
						self.console.print(f" - {failed}")

		def _register_failed(self, url):
			"""Record a URL that failed after exceeding maximum retries and update the progress bar."""
			self.failed_urls.append(url)
			try:
				# Advance the progress bar so the user sees progress even on failed items
				self.bar()
			except Exception:
				pass

		async def async_req(self, url, function=None, category=None):
			"""
			Perform an HTTP GET request with retry logic. If the request fails
			repeatedly, register the URL as failed rather than looping indefinitely.
			"""
			# Snapshot current connect/read timeouts for comparison inside auto_timeout
			timeout_ = [self.timeout.connect, self.timeout.sock_read]

			def auto_timeout(timeout, control, errors, e, add, which):
				"""
				Dynamically adjust timeouts if repeated read/connect errors occur.
				"""
				if errors[0] != 0:
					# Determine if the previous timeout change took effect
					if which == "connect":
						difference = timeout_[0] != self.oldtimeout[0]
					else:
						difference = timeout_[1] != self.oldtimeout[1]
					if difference:
						control[0] = 0
						errors[0] = 0
						return
					# If number of attempts per error is within threshold, increase timeout
					if control[0] // errors[0] <= e:
						self.oldtimeout = [self.timeout.connect, self.timeout.sock_read]
						timeout[0] += add
						control[0] = 0
						errors[0] = 0
						self.timeout = aiohttp.ClientTimeout(
							connect=self.timeout_connect[0],
							sock_read=self.timeout_read[0],
						)
						logger.info(f"timeout: {self.timeout}")
					else:
						control[0] = 0
						errors[0] = 0
				else:
					control[0] = 0
					errors[0] = 0

			# Limit the number of retries to avoid infinite recursion
			max_retries = 5

			async with self.sem:
				retries = 0
				while True:
					self.connect_control[0] += 1
					self.read_control[0] += 1
					# Adjust timeouts based on error counters
					if self.connect_control[0] // 10 >= 1:
						auto_timeout(
							self.timeout_connect,
							self.connect_control,
							self.connect_errors,
							4,
							8,
							"connect",
						)
					if self.read_control[0] // 10 >= 1:
						auto_timeout(
							self.timeout_read,
							self.read_control,
							self.read_errors,
							4,
							8,
							"read",
						)
					try:
						# Limit concurrent connections to 120 or reuse an existing one
						if len(self.connections_alive) < 120 or url in self.connections_alive:
							if url not in self.connections_alive:
								self.connections_alive.append(url)
							async with self.session.get(
								url, timeout=self.timeout, headers=self.headers, ssl=sslcontext
							) as resp:
								if resp.status == 200:
									# On success, remove connection and process result
									try:
										self.connections_alive.remove(url)
									except ValueError:
										pass
									if function:
										if "get_imgs" in repr(function):
											await function([await resp.read(), resp.status, url])
										else:
											if category is not None:
												await function([await resp.text(), resp.status, url, category])
											else:
												await function([await resp.text(), resp.status, url])
											# For album/category fetching, update progress bar here
											self.bar()
									return
								else:
									# Non-200 status codes: consider as retryable error
									retries += 1
									if retries > max_retries:
										logger.info(f"max retries (status) exceeded for {url}")
										self._register_failed(url)
										return
									await asyncio.sleep(0.5)
									continue
						else:
							# Too many alive connections; wait a bit and retry
							await asyncio.sleep(0.3)
							continue

					except self.FatalException:
						# Propagate fatal exceptions (like invalid link or no space)
						raise

					except TimeoutError:
						logger.info("error: TimeoutError")
						retries += 1
						if retries > max_retries:
							logger.info(f"max retries (TimeoutError) exceeded for {url}")
							self._register_failed(url)
							return
						continue

					except aiohttp.ServerDisconnectedError:
						logger.info("error: ServerDisconnectedError")
						retries += 1
						if retries > max_retries:
							logger.info(f"max retries (ServerDisconnectedError) exceeded for {url}")
							self._register_failed(url)
							return
						continue

					except aiohttp.ClientPayloadError:
						logger.info("error: ClientPayloadError")
						retries += 1
						if retries > max_retries:
							logger.info(f"max retries (ClientPayloadError) exceeded for {url}")
							self._register_failed(url)
							return
						continue

					except Exception as e:
						# Increment appropriate error counters to adjust timeouts
						err_str = str(e)
						if "Timeout on reading data from socket" in err_str:
							self.read_errors[0] += 1
						elif "Connection timeout to host" in err_str:
							self.connect_errors[0] += 1
						elif "Connect call failed" in err_str or "[WinError 10054]" in err_str:
							logger.info(e)
						elif url == err_str:
							# Invalid link exception
							self.error = 'link inválido!"'
							raise self.FatalException()
						elif "No space left on device" in err_str:
							# Out of disk space
							self.error = 'sem espaço no computador para baixar as imagens!"'
							raise self.FatalException()
						# Otherwise treat as retryable
						retries += 1
						if retries > max_retries:
							logger.info(f"max retries (other) exceeded for {url}: {e}")
							self._register_failed(url)
							return
						continue
				# End while
			# End async with

		async def get_pages(self, url_ = None):
			try:
				if self.all_albums:
					url = f"{self.urls}/albums?tab=gallery&page=1"
				else:
					url = f"{url_}?page=1"
					if "?" in url_:
						url = f"{url_}&page=1"
				
				timeout = aiohttp.ClientTimeout(total=15)
				session = aiohttp.ClientSession()
				async with session:
					while True:
						logging.info('getting pages')
						try:
							async with session.get(url, timeout=timeout, ssl=sslcontext) as resp:
								if resp.status == 200:
									logging.info('pages 200')
									text = await resp.text()
									soup = BeautifulSoup(text.encode("ascii", "ignore").decode("utf-8"), "lxml")
									if soup.select_one('div.empty_emptymain') == None:				
										try:
											total_pages = soup.select_one('form.pagination__jumpwrap input[name="page"]').get('max')
										except:
											total_pages = 1
										pages = []
										for page in range(1, int(total_pages)+1):
												pages.append(f"{url[:-1]}{page}")
										if type(pages) == list:
											if None in pages:
												await asyncio.sleep(0.2)
												return await self.get_pages(url_)
											else:
												if url_ != None:
													category_title = soup.select_one('.alert__title').text.replace("'", "").replace('"', '')
													return [pages, category_title]
												return pages
										elif pages == None:
											await asyncio.sleep(0.2)
											return await self.get_pages(url_)
										else:
											await asyncio.sleep(0.2)
											return await self.get_pages(url_)
									else:
										return None
								logger.info("getting pages again")
						except Exception as e:
							logging.info(f"getting pages again 2: {e}")
							pass
			except aiohttp.ClientConnectionError:
				if resp.status == 200:
					pass
				else:
					await asyncio.sleep(0.2)
					logger.info(f"pages exception: {e}")
					return await self.get_pages(url_)
			except Exception as e:
				await asyncio.sleep(0.2)
				logger.info(f"pages exception: {e}")
				return await self.get_pages(url_)

		async def get_albums(self, page):
			soup = BeautifulSoup(page[0].encode("ascii", "ignore").decode("utf-8"), "lxml")
			name_catalog = re.findall(r'(?<=https:\/\/)(.*?)(?=\.com)', page[2])[0]
			name_catalog = re.findall(r'(?<=^)(.*?)(?=\.x)', name_catalog)[0]
			if self.all_albums:
				if name_catalog not in self.albums:
					self.albums[name_catalog] = {}
				
			base_url = re.findall(r'(?<=https:\/\/)(.*?)(?=\.com)', page[2])[0]
			for album in soup.find_all("a", {"class": "album__main"}):
				href = album.get('href')
				rx = re.findall(r'(?<=\?)(.*?)(?=$)', href)
				rx = rx[0] if len(rx) > 0 else None
				new_href = href
				if rx != None:
					new_href = ''
					for i, st in enumerate(href.split(rx)):
						if st.strip() == '':
							continue
						if i != 0:
							new_href+=f' {st.strip()}'
						else:
							new_href+=st.strip()
					new_href += 'uid=1'

				title = (await self.parse_title(album.get('title'), name_catalog))
				if title == '':
					title = (await self.parse_title('blank', name_catalog))

				if self.all_albums:
					self.albums[name_catalog][title] = {"album_link": self.urls+new_href}
				else:
					self.albums[name_catalog][title] = {"album_link": f"https://{base_url}.com{new_href}", "category_title": page[3][0], "category_id": page[3][1]}


		async def get_album(self, r):
			name_catalog = re.findall(r'(?<=https:\/\/)(.*?)(?=\.com)', r[2])[0]
			name_catalog = re.findall(r'(?<=^)(.*?)(?=\.x)', name_catalog)[0]
			keys = (await self.find_key(self.albums, r[2]))
			keys = keys[0] if keys != None else None
			soup = BeautifulSoup(r[0].encode("ascii", "ignore").decode("utf-8"), "lxml")
			album_imgs_links = []
			if self.cover:
				cover = soup.select_one(".showalbumheader__gallerycover > img")
				src_cover = cover.get("src")
				src_cover = re.findall('/((?:(?!/).)*)/medium', src_cover)
			album_div = soup.find_all("div", {"class": "showalbum__children"})
			if len(album_div) == 0:
				self.error = 'não encontrado imagens no álbum, link potencialmente inválido!'
				raise self.FatalException()
			for img in album_div:
				typee_ = img.select_one(".image__imagewrap")
				if typee_.get("data-type") == "video":
					album_imgs_links.append(f"video")
					continue
				img = img.find("img")
				src = img.get("data-origin-src") #data-origin-src
				if self.cover:
					src_re = re.findall('/((?:(?!/).)*)/((?:(?!/).)*)\.((?:(?!\.).)*)$', src)
					if src_cover[0] == src_re[0][0]:
						album_imgs_links.append(f"https:{src}")
						break
					continue
				elif self.cover == False:
					album_imgs_links.append(f"https:{src}")
			# Associate the collected image links with the album in self.albums.
			if self.all_albums:
				# When crawling all albums from a catalog we already know the album key (keys[0], keys[1]).
				# Just assign the image list to this album.
				self.albums[keys[0]][keys[1]]['imgs'] = album_imgs_links
			else:
				# For user-specified album links (all_albums == False), derive a unique and descriptive album name.
				# If this album has not yet been encountered in this session, compute its title.
				if keys is None:
					# Ensure catalog dictionary exists
					if name_catalog not in self.albums:
						self.albums[name_catalog] = {}
					# Extract the raw title from the album page
					title_raw_el = soup.select_one("span.showalbumheader__gallerytitle")
					title_raw = title_raw_el.text.strip() if title_raw_el else ''
					# Fallback to 'blank' if the title is empty
					if not title_raw:
						title_raw = 'blank'
					# Extract album code from the URL (e.g., albums/123456789)
					match = re.search(r'albums/(\d+)', r[2])
					album_code = match.group(1) if match else None
					# Combine code and raw title to form a base title
					combined_title = f"{album_code}_{title_raw}" if album_code else title_raw
					# Sanitize and ensure uniqueness within this catalog (and avoid overwriting existing folders on disk)
					title = await self.parse_title(combined_title, name_catalog)
				else:
					# Use existing title if already stored
					title = keys[1]
				# Initialize album entry if not present
				if title not in self.albums[name_catalog]:
					self.albums[name_catalog][title] = {}
					self.albums[name_catalog][title]["album_link"] = r[2]
				# Store the list of image links
				self.albums[name_catalog][title]["imgs"] = album_imgs_links

		async def get_imgs(self, r):
			keys = (await self.find_key(self.albums, r[2]))[0]
			album_path = self.albums[keys[0]][keys[1]]
			album = keys[1]
			try:
				img_title = re.findall(r'/((?:(?!/).)*)$', r[2])[0].split('.')[0] #/((?:(?!/).)*)$
			except:
				return

			name_catalog = keys[0]
			path = f"{OUTPUT_PATH}/fotos_yupoo/{name_catalog}/albuns/{album}"
			if os.path.exists(path) == False:
				os.makedirs(path)
			
			if "category_title" in album_path:
				save_path = self.normpath(f"{OUTPUT_PATH}/fotos_yupoo/{name_catalog}/categorias/{album_path['category_title']}/")
				target = self.normpath(path)  # The shortcut target file or folder
				work_dir = self.normpath(f"{OUTPUT_PATH}/fotos_yupoo/{name_catalog}/albuns/")  # The parent folder of your file
			else:
				save_path = self.normpath(f"{OUTPUT_PATH}/fotos_yupoo/{name_catalog}/categorias/sem categoria/")
				target = self.normpath(path)  # The shortcut target file or folder
				work_dir = self.normpath(f"{OUTPUT_PATH}/fotos_yupoo/{name_catalog}/albuns/")  # The parent folder of your file

			# Create a shortcut or symlink pointing to the album directory
			self.create_shortcut(save_path, album, target, work_dir)

			try:
				async with aiofiles.open(f'{OUTPUT_PATH}/fotos_yupoo/{name_catalog}/albuns/{album}/{img_title}.jpeg', mode='wb') as f:
					img = Image.open(BytesIO(r[0]))
					img = img.convert('RGB')
					if "exif" in img.info:
						try:
							exif_dict = piexif.load(img.info["exif"])
							del exif_dict['thumbnail']
							del exif_dict['1st']
							try:
								del exif_dict['Exif'][piexif.ExifIFD.SceneType]
							except:
								pass
							if piexif.ImageIFD.Orientation in exif_dict["0th"]:
								orientation = exif_dict["0th"].pop(piexif.ImageIFD.Orientation)
								exif_bytes = piexif.dump(exif_dict)

								if orientation == 2:
									img = img.transpose(Image.FLIP_LEFT_RIGHT)
								elif orientation == 3:
									img = img.rotate(180)
								elif orientation == 4:
									img = img.rotate(180).transpose(Image.FLIP_LEFT_RIGHT)
								elif orientation == 5:
									img = img.rotate(-90, expand=True).transpose(Image.FLIP_LEFT_RIGHT)
								elif orientation == 6:
									img = img.rotate(-90, expand=True)
								elif orientation == 7:
									img = img.rotate(90, expand=True).transpose(Image.FLIP_LEFT_RIGHT)
								elif orientation == 8:
									img = img.rotate(90, expand=True)

								img_byte_arr = BytesIO()
								img.save(img_byte_arr, exif=exif_bytes, format='JPEG')
								img_byte_arr = img_byte_arr.getvalue()
								await f.write(img_byte_arr)
						except Exception as e:
							keys = (await self.find_key(self.albums, r[2]))[0]
							key = self.albums[keys[0]][keys[1]]['album_link']
							if 'unpack requires a buffer of' in repr(e):
								logger.info(f'{e}:  [{key}, {r[2]}]')
								await f.write(r[0])
							else:
								logger.info(f'{traceback.format_exc()}')
								logger.info(f'{e}:  [{key}, {r[2]}]')
								try:
									await f.write(r[0])
								except:
									# If writing fails, register failure and skip this image
									self._register_failed(r[2])
									self.error = e
									return
						else:
							await f.write(r[0])
					else:
						await f.write(r[0])
				self.bar()
			except Exception as e:
				# Locate the album and mark this image as failed
				keys = (await self.find_key(self.albums, r[2]))[0]
				key = self.albums[keys[0]][keys[1]]['album_link']
				logger.info(traceback.format_exc())
				logger.info(f'error write file URL: [{key}, {r[2]}]')
				self.error = f'error write file: {e}'
				# Register this image link as failed and skip without aborting
				self._register_failed(r[2])
				return

		async def _(self, tasks, function = None):
			try:
				self.connections_alive = []
				resp = await asyncio.gather(*tasks)
				return resp
			except self.FatalException:
				for task in self.tasks:
					task.cancel()
				raise Exception(self.error)


		async def parse_title(self, title, catalog, category = False):
			title = title.replace('.', '_').replace('/', '_').replace(':', '').replace('"', '').replace("'", '').replace('*','')
			title = title.strip()
			it = 0
			while True:
				it += 1
				# Construct candidate title: first attempt uses the base title,
				# subsequent attempts append ' - N' suffix.
				candidate = title if it == 1 else f"{title} - {str(it)}"
				if category:
					# When naming category folders, ensure we don't reuse a title
					# that already has a category_title assigned.
					keys_list = await self.find_key(self.albums[catalog], candidate)
					have_title = False
					if keys_list is not None:
						for keys in keys_list:
							if keys[-1] == "category_title":
								have_title = True
								break
					if not have_title:
						return candidate
				else:
					# For album folders, ensure the title is not already used in this session
					# and that no existing folder on disk has the same name.
					existing_session = candidate in self.albums.get(catalog, {})
					# Build path to the potential album directory.
					album_path = os.path.join(OUTPUT_PATH, "fotos_yupoo", catalog, "albuns", candidate)
					existing_disk = os.path.exists(album_path)
					if not existing_session and not existing_disk:
						return candidate
				# Otherwise, loop to next candidate

		async def find_key(self, d: dict, value):
			d, value = deepcopy(d), deepcopy(value)
			def _k(d: dict, value):
				for k,v in d.items():
					if isinstance(v, dict):
							p = _k(v, value)
							if p:
								return [k] + p
					elif isinstance(v, list) == True and k == "imgs":
						if value in v:
							v.remove(value)
							return [k]
					elif v == value:
							del d[k]
							return [k]
			keys = []
			while True:
				k = _k(d, value)
				if k != None:
					keys.append(k)
				else:
					break
			if len(keys) == 0:
				return None
			return keys