import hashlib

from hhutil.io import PathLike

BUF_SIZE = 64 * 1024

def hash_file(fp: PathLike, method='sha256'):
    obj = getattr(hashlib, method)()

    with open(fp, 'rb') as f:
        while True:
            data = f.read(BUF_SIZE)
            if not data:
                break
            obj.update(data)
    
    return obj.hexdigest()


def sha256(fp: PathLike):
    return hash_file(fp, "sha256")


def md5(fp: PathLike):
    return hash_file(fp, "md5")
