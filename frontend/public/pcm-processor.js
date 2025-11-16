// public/pcm-processor.js
class PCMProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.buffer = [];
    this.chunkSamples = Math.floor(sampleRate * 0.25);
    this.chunkCount = 0;
    console.log(`[PCMProcessor] Initialized at ${sampleRate}Hz`);
    console.log(`[PCMProcessor] Chunk size: ${this.chunkSamples} samples (250ms)`);
  }

  process(inputs) {
    const input = inputs[0];
    
    if (!input || !input[0]) {
      console.warn('[PCMProcessor] No input received');
      return true;
    }
    
    const samples = input[0];
    
    // Check for silence
    const rms = Math.sqrt(
      samples.reduce((sum, val) => sum + val * val, 0) / samples.length
    );
    
    // // Log very quiet audio
    // if (rms < 0.001) {
    //   console.warn(`[PCMProcessor] Very quiet input: RMS=${rms.toFixed(6)}`);
    // }
    
    this.buffer.push(...samples);

    while (this.buffer.length >= this.chunkSamples) {
      const chunk = this.buffer.splice(0, this.chunkSamples);
      const chunkArray = new Float32Array(chunk);
      
      // Calculate chunk RMS
      const chunkRms = Math.sqrt(
        chunkArray.reduce((sum, val) => sum + val * val, 0) / chunkArray.length
      );
      
      this.chunkCount++;
      // console.log(`[PCMProcessor] Chunk #${this.chunkCount}: ${chunkArray.length} samples, RMS=${chunkRms.toFixed(4)}`);
      
      this.port.postMessage(chunkArray);
    }

    return true;
  }
}

registerProcessor("pcm-processor", PCMProcessor);