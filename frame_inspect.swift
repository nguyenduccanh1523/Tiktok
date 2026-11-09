import AVFoundation
import AppKit

let args = CommandLine.arguments
guard args.count >= 3 else {
    print("Usage: frame_inspect <video_path> <time_sec> <out_jpg>")
    exit(1)
}

let videoPath = args[1]
let timeSec = Double(args[2]) ?? 0.0
let outPath = args[3]

let url = URL(fileURLWithPath: videoPath)
let asset = AVAsset(url: url)
let generator = AVAssetImageGenerator(asset: asset)
generator.appliesPreferredTrackTransform = true
generator.requestedTimeToleranceBefore = .zero
generator.requestedTimeToleranceAfter = .zero

let time = CMTime(seconds: timeSec, preferredTimescale: 600)
do {
    let cgImage = try generator.copyCGImage(at: time, actualTime: nil)
    let rep = NSBitmapImageRep(cgImage: cgImage)
    if let data = rep.representation(using: .jpeg, properties: [:]) {
        try data.write(to: URL(fileURLWithPath: outPath))
        print("Saved frame at \(timeSec)s to \(outPath) (\(data.count) bytes)")
    }
} catch {
    print("Error: \(error)")
    exit(1)
}
