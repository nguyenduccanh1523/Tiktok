import Foundation
import AVFoundation

func processToAdamStyle(inputPath: String, outputWavPath: String, pitchCents: Float = -240.0, rate: Float = 1.25) throws {
    let inURL = URL(fileURLWithPath: inputPath)
    let outURL = URL(fileURLWithPath: outputWavPath)
    try? FileManager.default.removeItem(at: outURL)

    let inputFile = try AVAudioFile(forReading: inURL)
    let format = inputFile.processingFormat

    let engine = AVAudioEngine()
    let player = AVAudioPlayerNode()
    let timePitch = AVAudioUnitTimePitch()
    timePitch.pitch = pitchCents
    timePitch.rate = rate

    engine.attach(player)
    engine.attach(timePitch)
    engine.connect(player, to: timePitch, format: format)
    engine.connect(timePitch, to: engine.mainMixerNode, format: format)

    try engine.enableManualRenderingMode(.offline, format: format, maximumFrameCount: 4096)
    try engine.start()
    player.play()

    player.scheduleFile(inputFile, at: nil, completionHandler: nil)

    let outputFile = try AVAudioFile(
        forWriting: outURL,
        settings: engine.manualRenderingFormat.settings,
        commonFormat: engine.manualRenderingFormat.commonFormat,
        interleaved: engine.manualRenderingFormat.isInterleaved
    )
    let buffer = AVAudioPCMBuffer(pcmFormat: engine.manualRenderingFormat, frameCapacity: engine.manualRenderingMaximumFrameCount)!

    let targetFrames = AVAudioFramePosition(Double(inputFile.length) / Double(rate)) + 2048

    while engine.manualRenderingSampleTime < targetFrames {
        let status = try engine.renderOffline(buffer.frameCapacity, to: buffer)
        if status == .success {
            try outputFile.write(from: buffer)
        } else {
            break
        }
    }

    player.stop()
    engine.stop()
}

if CommandLine.arguments.count >= 3 {
    let pitch: Float = CommandLine.arguments.count >= 4 ? (Float(CommandLine.arguments[3]) ?? -240.0) : -240.0
    let rate: Float = CommandLine.arguments.count >= 5 ? (Float(CommandLine.arguments[4]) ?? 1.25) : 1.25
    do {
        try processToAdamStyle(inputPath: CommandLine.arguments[1], outputWavPath: CommandLine.arguments[2], pitchCents: pitch, rate: rate)
        print("ADAM_VOICE_OK")
    } catch {
        fputs("Error: \(error)\n", stderr)
        exit(1)
    }
}
