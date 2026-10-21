# Third-party notices

Hymio uses installed Python packages without copying their implementation into the repository. Their license files remain in the Python distribution and container image.

## Document conversion

[Microsoft MarkItDown](https://github.com/microsoft/markitdown), MIT License, copyright Microsoft Corporation. Used through its Python API with plugins disabled. Optional converters include Mammoth (BSD-2-Clause), python-pptx and openpyxl (MIT), xlrd and pandas (BSD), pdfminer.six/pdfplumber (MIT), and pypdfium2 (BSD-3-Clause/Apache-2.0 with PDFium dependency notices). Keep the corresponding package license files and PDFium notices when redistributing binaries; do not remove `.dist-info/licenses` or pypdfium2's licensing directory from packaged environments.

MarkItDown license:

MIT License

Copyright (c) Microsoft Corporation.

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

## Cloud desktop SDK

[Daytona Python SDK](https://github.com/daytonaio/daytona), Apache License 2.0. Used as an installed dependency for sandbox lifecycle and desktop control. Preserve the SDK distribution’s LICENSE and any NOTICE files when redistributing containers or packaged environments. Hymio does not vendor its implementation.
