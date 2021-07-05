import os
import re
import pickle
import sys
import stat
import json
import shutil
import tempfile
import zipfile
import importlib.util
from pathlib import Path
from typing import Callable, Any, Union, Sequence
from datetime import datetime, timedelta

import requests

PathLike = Union[str, Path]


def read_lines(fp: PathLike):
    return fmt_path(fp).read_text().splitlines()


def write_lines(lines: Sequence[str], fp: PathLike):
    fmt_path(fp).write_text(os.linesep.join(lines))
    return fp


def write_text(text: str, fp: PathLike):
    fmt_path(fp).write_text(text)
    return fp


def read_text(fp):
    return fmt_path(fp).read_text()


def read_pickle(fp: PathLike):
    with open(fp, 'rb') as f:
        data = pickle.load(f)
    return data


def save_pickle(obj, fp: PathLike):
    with open(fp, 'wb') as f:
        pickle.dump(obj, f)


def read_json(fp: PathLike):
    with open(fp) as f:
        data = json.load(f)
    return data


def save_json(obj, fp: PathLike):
    with open(fp, 'w') as f:
        json.dump(obj, f)


def fmt_path(fp: PathLike) -> Path:
    return Path(fp).expanduser().absolute()


def is_hidden(fp: PathLike):
    fp = fmt_path(fp)
    plat = sys.platform
    if plat == 'darwin':
        import Foundation
        url = Foundation.NSURL.fileURLWithPath_(str(fp))
        return url.getResourceValue_forKey_error_(None, Foundation.NSURLIsHiddenKey, None)[1]
    elif plat in ['win32', 'cygwin']:
        return bool(fp.stat().st_file_attributes & stat.FILE_ATTRIBUTE_HIDDEN)
    else:
        return fp.name.startswith(".")


def eglob(fp: PathLike, pattern: str):
    fp = fmt_path(fp)
    for f in fp.glob(pattern):
        if not is_hidden(f):
            yield f


def apply_dir(dir: PathLike, f: Callable[[PathLike], Any], suffix=None, recursive=True) -> None:
    dir = fmt_path(dir)
    for fp in dir.iterdir():
        if fp.name.startswith('.'):
            continue
        elif fp.is_dir():
            if recursive:
                apply_dir(fp, f, recursive, suffix)
        elif fp.is_file():
            if suffix is None:
                f(fp)
            elif fp.suffix == suffix:
                f(fp)


def rename(fp: PathLike, new_name: str, stem=True):
    fp = fmt_path(fp)
    if stem:
        fp.rename(fp.parent / (new_name + fp.suffix))
    else:
        fp.rename(fp.parent / new_name)


def copy(src: PathLike, dst: PathLike):
    src = fmt_path(src)
    dst = fmt_path(dst)
    shutil.copy(str(src), str(dst))


def mv(src: PathLike, dst: PathLike):
    return fmt_path(shutil.move(str(src), str(dst)))


def rm(fp: PathLike):
    fp = fmt_path(fp)
    if fp.exists():
        if fp.is_dir():
            for d in fp.iterdir():
                rm(d)
            fp.rmdir()
        else:
            fp.unlink()


def time_now():
    now = datetime.utcnow() + timedelta(hours=8)
    now = now.strftime("%H:%M:%S")
    return now


def parse_python_config(fp: PathLike):
    spec = importlib.util.spec_from_file_location("config", fp)
    cfg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cfg)
    return cfg


def _zip_add_directory(zip_file, path, zip_path):
    for item in sorted(os.listdir(path)):
        current_path = os.path.join(path, item)
        current_zip_path = os.path.join(zip_path, item)
        if os.path.isfile(current_path):
            _zip_add_file(zip_file, current_path, current_zip_path)
        else:
            _zip_add_directory(zip_file, current_path, current_zip_path)


def _zip_add_file(zip_file, path, zip_path=None):
    permission = 0o555 if os.access(path, os.X_OK) else 0o444
    zip_info = zipfile.ZipInfo.from_file(path, zip_path)
    zip_info.date_time = (2019, 1, 1, 0, 0, 0)
    zip_info.external_attr = (stat.S_IFREG | permission) << 16
    with open(path, "rb") as fp:
        zip_file.writestr(
            zip_info,
            fp.read(),
            compress_type=zipfile.ZIP_DEFLATED,
            compresslevel=9,
        )


def zip_files(fps, dst, deterministic=False):
    zf = zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED)
    for fp in fps:
        fp = fmt_path(fp)
        if deterministic:
            _zip_add_file(zf, str(fp), fp.name)
        else:
            zf.write(str(fp), fp.name)
    zf.close()


def zip_dir(fp, dst):
    fp = fmt_path(fp)
    dst = fmt_path(dst)
    base_name = dst.parent / dst.stem
    shutil.make_archive(base_name, 'zip', fp)


def unzip(fp, dst):
    with zipfile.ZipFile(fp, 'r') as f:
        f.extractall(dst)


def _parse_response_filename(rep):
    s = rep.headers['Content-Disposition']
    key = "filename="
    p = s.find(key)
    if p == -1:
        return None
    p = p + len(key)
    filename = s[p:]
    if filename[0] == '"' and filename[-1] == '"':
        filename = filename[1:-1]
    return filename


def download_file(url, dst, headers=None):
    dst = fmt_path(dst)
    if dst.exists() and dst.is_dir():
        dst_dir = dst
        filename = None
    else:
        dst_dir = dst.parent
        filename = dst.name
    f = tempfile.NamedTemporaryFile(delete=False, dir=dst_dir)
    try:
        with requests.get(url, stream=True, headers=headers) as r:
            r.raw.decode_content = True
            shutil.copyfileobj(r.raw, f)
            if filename is None:
                filename = _parse_response_filename(r)
        f.close()
        if filename is not None:
            dst = dst_dir / filename
            shutil.move(f.name, dst)
        else:
            # Can't parse filename and target is dir, use temp file name
            pass
    finally:
        f.close()
        if os.path.exists(f.name):
            os.remove(f.name)
    return dst


def download_github_private_assert(url, dst, access_token):
    p = r"https://github.com/([a-zA-Z0-9]+)/([a-z0-9A-Z-_]+)/releases/download/([0-9\.]+)/(.*)"
    m = re.match(p, url)
    assert m is not None and len(m.groups()) == 4
    repo = m.group(1) + "/" + m.group(2)
    tag = m.group(3)
    file = m.group(4)
    query_url = f"https://api.github.com/repos/{repo}/releases/tags/{tag}"
    headers = {
        "Authorization": f"token {access_token}",
        "Accept": "application/vnd.github.v3+json"
    }
    req = requests.get(query_url, headers=headers)
    asset_id = next(filter(lambda a: a['name'] == file, req.json()['assets']))['id']
    download_url = f"https://api.github.com/repos/{repo}/releases/assets/{asset_id}"
    headers = {
        "Authorization": f"token {access_token}",
        "Accept": "application/octet-stream"
    }
    return download_file(download_url, dst, headers=headers)


def get_onedrive_download_url(share_url):
    p = r"https://1drv\.ms/u/s!([0-9a-zA-Z-_]{28})\?e=[0-9a-zA-Z-_]{6}"
    m = re.match(p, share_url)
    if m is None:
        raise ValueError("Error share url: %s" % share_url)
    share_id = m.group(1)
    download_url = f"https://api.onedrive.com/v1.0/shares/s!{share_id}/root/content"
    return download_url


def download_from_onedrive(share_url, dst):
    download_url = get_onedrive_download_url(share_url)
    return download_file(download_url, dst)
