# Third-party components and data

The root MIT license applies to this project's original source and documentation.
It does not relicense third-party libraries, services, datasets or model weights.

Dependencies are installed from upstream packages, not copied into this repository.
See `requirements.txt`, `requirements-optional.txt` and `web/package-lock.json`
for pinned versions, and each installed package's license and notices for its terms.
Major upstream projects include:

- [FastAPI](https://github.com/fastapi/fastapi), [SQLAlchemy](https://github.com/sqlalchemy/sqlalchemy), [Pydantic](https://github.com/pydantic/pydantic).
- [NumPy](https://github.com/numpy/numpy), [Pillow](https://github.com/python-pillow/Pillow), [OR-Tools](https://github.com/google/or-tools).
- [Vue](https://github.com/vuejs/core), [Vite](https://github.com/vitejs/vite), [Lucide](https://github.com/lucide-icons/lucide).
- Optional [PyTorch](https://github.com/pytorch/pytorch), [torchvision](https://github.com/pytorch/vision), [Chinese-CLIP](https://github.com/OFA-Sys/Chinese-CLIP), and Alibaba Cloud SDK.

Model weights are downloaded separately. Review the relevant model and training
data terms before deployment or redistribution; they are not included in the
MIT grant for this repository. No third-party merchant photos or original course
documents are included. Procedural fixture generators are original project code;
generated fixtures illustrate algorithms and are not real commercial offers.

Imported images require recorded sources and authorization. WeChat and Alibaba
Cloud integrations require the operator's own account and service configuration.
This repository grants no rights to those platforms or their data.
