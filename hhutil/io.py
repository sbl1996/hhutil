import os
import pickle
import sys
import stat
import json
import shutil
import tempfile
from zipfile import ZipFile, ZIP_DEFLATED
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


def zip_files(fps, dst):
    zf = ZipFile(dst, "w", ZIP_DEFLATED)
    for fp in fps:
        fp = fmt_path(fp)
        zf.write(str(fp), fp.name)
    zf.close()


def zip_dir(fp, dst):
    fp = fmt_path(fp)
    dst = fmt_path(dst)
    base_name = dst.parent / dst.stem
    shutil.make_archive(base_name, 'zip', fp)


def unzip(fp, dst):
    with ZipFile(fp, 'r') as f:
        f.extractall(dst)


def download_file(url, dst):
    dst_dir = fmt_path(dst).parent
    f = tempfile.NamedTemporaryFile(delete=False, dir=dst_dir)
    try:
        with requests.get(url, stream=True) as r:
            r.raw.decode_content = True
            shutil.copyfileobj(r.raw, f)
        f.close()
        shutil.move(f.name, dst)
    finally:
        f.close()
        if os.path.exists(f.name):
            os.remove(f.name)
    return dst


