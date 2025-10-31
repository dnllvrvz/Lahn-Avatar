// public/pcm-processor.js
class PCMProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.buffer = [];
    this.chunkSamples = 24000 * 0.25; // 250 ms of audio at 24 kHz
  }

  process(inputs) {
    const input = inputs[0][0];
    if (!input) return true;

    // Push samples into buffer
    this.buffer.push(...input);

    // Send every 250 ms
    if (this.buffer.length >= this.chunkSamples) {
      const chunk = this.buffer.splice(0, this.chunkSamples);
      this.port.postMessage(chunk);
    }

    return true; // keep processor alive
  }
}

registerProcessor("pcm-processor", PCMProcessor);
