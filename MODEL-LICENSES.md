# Voxora model notices

Voxora downloads and runs the following third-party model weights locally. The weights are not included in this Git repository. Each model has its own licence; the Voxora application licence does not replace these terms.

| Language | Model | Licence | Source |
|---|---|---|---|
| English | F5-TTS v1 Base weights | CC BY-NC 4.0 | [SWivid/F5-TTS](https://huggingface.co/SWivid/F5-TTS) |
| Hindi | SPRINGLab F5-Hindi-24KHz | CC BY 4.0 | [SPRINGLab/F5-Hindi-24KHz](https://huggingface.co/SPRINGLab/F5-Hindi-24KHz) |
| Kannada | F5-TTS OpenBible Kannada | CC BY-SA 4.0 | [multilingual-tts/F5-TTS-OpenBible-Kannada](https://huggingface.co/multilingual-tts/F5-TTS-OpenBible-Kannada) |
| Vocos vocoder | charactr/vocos-mel-24khz | See upstream model repository | [charactr/vocos-mel-24khz](https://huggingface.co/charactr/vocos-mel-24khz) |

The F5-TTS application code is MIT-licensed, but the English pretrained weights are CC BY-NC 4.0 and are restricted to non-commercial use. Do not assume the application MIT licence grants commercial rights to the model weights.

Hindi model attribution: SPRING Lab, Indian Institute of Technology Madras.

Kannada source checkpoint: model_last.pt, distributed under CC BY-SA 4.0. The local development machine may use an EMA-only safetensors conversion of this checkpoint; new installations download the original published checkpoint and let F5-TTS select its EMA weights.

Review the linked model cards and their licence files before redistributing weights, fine-tunes, or generated datasets. Model licences can change independently of this project.
