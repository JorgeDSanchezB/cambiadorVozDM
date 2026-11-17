// Codificador WAV PCM16 little-endian (para descargar lecturas renderizadas,
// espejo del WAV del escritorio en data/lectura/).

export function audioBufferAWav(buffer: AudioBuffer): Blob {
  const numCanales = buffer.numberOfChannels
  const sr = buffer.sampleRate
  const numMuestras = buffer.length
  const bytesPorMuestra = 2
  const bytesDatos = numMuestras * numCanales * bytesPorMuestra
  const arrayBuffer = new ArrayBuffer(44 + bytesDatos)
  const vista = new DataView(arrayBuffer)

  const escribirTexto = (pos: number, texto: string) => {
    for (let i = 0; i < texto.length; i++) vista.setUint8(pos + i, texto.charCodeAt(i))
  }

  escribirTexto(0, 'RIFF')
  vista.setUint32(4, 36 + bytesDatos, true)
  escribirTexto(8, 'WAVE')
  escribirTexto(12, 'fmt ')
  vista.setUint32(16, 16, true)
  vista.setUint16(20, 1, true) // PCM
  vista.setUint16(22, numCanales, true)
  vista.setUint32(24, sr, true)
  vista.setUint32(28, sr * numCanales * bytesPorMuestra, true)
  vista.setUint16(32, numCanales * bytesPorMuestra, true)
  vista.setUint16(34, 16, true)
  escribirTexto(36, 'data')
  vista.setUint32(40, bytesDatos, true)

  const canales: Float32Array[] = []
  for (let c = 0; c < numCanales; c++) canales.push(buffer.getChannelData(c))

  let pos = 44
  for (let i = 0; i < numMuestras; i++) {
    for (let c = 0; c < numCanales; c++) {
      let v = canales[c][i]
      if (v > 1) v = 1
      else if (v < -1) v = -1
      vista.setInt16(pos, v < 0 ? v * 0x8000 : v * 0x7fff, true)
      pos += 2
    }
  }
  return new Blob([arrayBuffer], { type: 'audio/wav' })
}

export function marcaDeTiempo(): string {
  // Espejo del patrón de config.json: voz_{fecha}_{hora}
  const ahora = new Date()
  const p = (n: number) => String(n).padStart(2, '0')
  return `${ahora.getFullYear()}${p(ahora.getMonth() + 1)}${p(ahora.getDate())}_${p(ahora.getHours())}${p(ahora.getMinutes())}${p(ahora.getSeconds())}`
}

export function descargarBlob(blob: Blob, nombre: string): void {
  const url = URL.createObjectURL(blob)
  const ancla = document.createElement('a')
  ancla.href = url
  ancla.download = nombre
  document.body.appendChild(ancla)
  ancla.click()
  ancla.remove()
  setTimeout(() => URL.revokeObjectURL(url), 5000)
}
