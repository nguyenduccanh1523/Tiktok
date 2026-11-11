import Foundation
import AVFoundation
import AppKit
import CoreGraphics

struct SceneSpec: Codable {
    let image_path: String
    let video_path: String?
    let video_start_sec: Double?
    let audio_path: String?
    let motion: String
    let duration_sec: Double
}

struct RenderManifest: Codable {
    let audio_path: String
    let output_mp4_path: String
    let scenes: [SceneSpec]
}

func loadCGImage(path: String) -> CGImage? {
    let url = URL(fileURLWithPath: path)
    guard let src = CGImageSourceCreateWithURL(url as CFURL, nil) else { return nil }
    return CGImageSourceCreateImageAtIndex(src, 0, nil)
}

struct VideoBundle {
    let sharp: CGImage
    let blur: CGImage?
}

func drawProHandheldShot(
    _ ctx: CGContext,
    img: CGImage,
    blurImg: CGImage? = nil,
    width: CGFloat,
    height: CGFloat,
    motion: String,
    progress: Double,
    globalTimeSec: Double,
    alpha: CGFloat = 1.0,
    isRealVideoFrame: Bool = false
) {
    ctx.saveGState()
    ctx.setAlpha(alpha)

    let imgAspect = CGFloat(img.width) / CGFloat(max(1, img.height))

    if isRealVideoFrame {
        ctx.interpolationQuality = .high
        ctx.setShouldAntialias(true)

        let smoothT = CGFloat(0.5 - 0.5 * cos(progress * Double.pi))

        // === 100% VIDEO DỌC TOÀN MÀN HÌNH CHUẨN TIKTOK (9:16) ===
        // Tràn màn hình 100%, không viền đen, không mờ dải ngang giả tạo kiểu quảng cáo
        // Tập trung toàn bộ vào đôi tay thao tác & chi tiết sản phẩm thực tế
        var cropZoom: CGFloat = 1.05
        var panX: CGFloat = 0.0
        var panY: CGFloat = 0.0

        switch motion {
        case "zoom_out":
            cropZoom = 1.08 - smoothT * 0.04
            panY = (0.5 - smoothT) * 10.0
        case "pan_detail":
            cropZoom = 1.06
            panX = (0.5 - smoothT) * 14.0
        case "focus_center":
            cropZoom = 1.05 + sin(smoothT * CGFloat.pi) * 0.02
        default: // zoom_in
            cropZoom = 1.05 + smoothT * 0.04
            panY = (smoothT - 0.5) * 10.0
        }

        var drawW = width * cropZoom
        var drawH = drawW / imgAspect
        if drawH < height * cropZoom {
            drawH = height * cropZoom
            drawW = drawH * imgAspect
        }
        let rect = CGRect(
            x: (width - drawW) / 2.0 + panX,
            y: (height - drawH) / 2.0 + panY,
            width: drawW,
            height: drawH
        )
        ctx.draw(img, in: rect)
        ctx.restoreGState()
        return
    }

    // Fallback for static image: Smooth S-curve + Whip-zoom speed ramp
    let smoothT = 0.5 - 0.5 * cos(progress * Double.pi)
    let entryBoost = pow(max(0.0, 1.0 - progress * 4.5), 2.0) * 0.14
    let exitBoost = pow(max(0.0, (progress - 0.78) / 0.22), 2.0) * 0.16

    let swayX = CGFloat(sin(globalTimeSec * 2.7) * 14.0 + cos(globalTimeSec * 1.3) * 8.0)
    let swayY = CGFloat(cos(globalTimeSec * 2.3) * 12.0 + sin(globalTimeSec * 3.1) * 6.0)
    let swayAngle = CGFloat(sin(globalTimeSec * 1.9) * 0.012)

    var baseScale: CGFloat = 1.08
    var panX: CGFloat = 0
    var panY: CGFloat = 0

    let isMacroCut = progress > 0.52
    let cutPunch: CGFloat = isMacroCut ? 0.16 : 0.0

    switch motion {
    case "zoom_out":
        baseScale = 1.28 - CGFloat(smoothT) * 0.18 + CGFloat(entryBoost)
        panX = isMacroCut ? -35.0 : 20.0
        panY = CGFloat(0.5 - smoothT) * 45.0
    case "pan_detail":
        baseScale = 1.18 + cutPunch + CGFloat(entryBoost)
        panX = CGFloat(0.5 - smoothT) * 110.0
        panY = CGFloat(smoothT - 0.5) * 65.0
    case "focus_center":
        baseScale = 1.10 + CGFloat(sin(smoothT * Double.pi)) * 0.14 + CGFloat(exitBoost)
        panX = CGFloat(sin(smoothT * Double.pi * 2.0)) * 35.0
        panY = 0
    default: // zoom_in
        baseScale = 1.06 + CGFloat(smoothT) * 0.22 + cutPunch + CGFloat(entryBoost + exitBoost)
        panX = isMacroCut ? 30.0 : -15.0
        panY = CGFloat(smoothT - 0.5) * 40.0
    }

    var bgW = width * 1.35
    var bgH = bgW / imgAspect
    if bgH < height * 1.35 {
        bgH = height * 1.35
        bgW = bgH * imgAspect
    }
    ctx.saveGState()
    ctx.setAlpha(alpha * 0.38)
    ctx.draw(img, in: CGRect(x: (width - bgW) / 2.0 - swayX, y: (height - bgH) / 2.0 - swayY, width: bgW, height: bgH))
    ctx.restoreGState()

    ctx.setFillColor(NSColor(calibratedWhite: 0.0, alpha: 0.45 * alpha).cgColor)
    ctx.fill(CGRect(x: 0, y: 0, width: width, height: height))

    ctx.translateBy(x: width / 2.0 + panX + swayX, y: height / 2.0 + panY + swayY)
    ctx.rotate(by: swayAngle)

    var fgW = width * baseScale
    var fgH = fgW / imgAspect
    if fgH < height * 0.82 {
        fgH = height * 0.82
        fgW = fgH * imgAspect
    }

    let fgRect = CGRect(x: -fgW / 2.0, y: -fgH / 2.0, width: fgW, height: fgH)
    ctx.draw(img, in: fgRect)
    ctx.restoreGState()
}

func createCleanPixelBuffer(
    pool: CVPixelBufferPool,
    width: Int,
    height: Int,
    currentImage: CGImage?,
    currentBlurImage: CGImage? = nil,
    nextImage: CGImage?,
    currentMotion: String,
    nextMotion: String,
    progress: Double,
    globalTimeSec: Double,
    crossfadeAlpha: Double,
    isRealVideoFrame: Bool
) -> CVPixelBuffer? {
    var pb: CVPixelBuffer?
    let status = CVPixelBufferPoolCreatePixelBuffer(kCFAllocatorDefault, pool, &pb)
    guard status == kCVReturnSuccess, let pixelBuffer = pb else { return nil }

    CVPixelBufferLockBaseAddress(pixelBuffer, [])
    defer { CVPixelBufferUnlockBaseAddress(pixelBuffer, []) }

    guard let baseAddress = CVPixelBufferGetBaseAddress(pixelBuffer) else { return nil }
    let bytesPerRow = CVPixelBufferGetBytesPerRow(pixelBuffer)
    let colorSpace = CGColorSpaceCreateDeviceRGB()

    guard let ctx = CGContext(
        data: baseAddress,
        width: width,
        height: height,
        bitsPerComponent: 8,
        bytesPerRow: bytesPerRow,
        space: colorSpace,
        bitmapInfo: CGImageAlphaInfo.premultipliedFirst.rawValue | CGBitmapInfo.byteOrder32Little.rawValue
    ) else { return nil }

    let W = CGFloat(width)
    let H = CGFloat(height)

    ctx.setFillColor(NSColor.black.cgColor)
    ctx.fill(CGRect(x: 0, y: 0, width: W, height: H))

    if let img = currentImage {
        drawProHandheldShot(
            ctx,
            img: img,
            blurImg: currentBlurImage,
            width: W,
            height: H,
            motion: currentMotion,
            progress: progress,
            globalTimeSec: globalTimeSec,
            alpha: 1.0,
            isRealVideoFrame: isRealVideoFrame
        )
    }

    if crossfadeAlpha > 0.0, let nxt = nextImage {
        drawProHandheldShot(
            ctx,
            img: nxt,
            blurImg: nil,
            width: W,
            height: H,
            motion: nextMotion,
            progress: 0.0,
            globalTimeSec: globalTimeSec,
            alpha: CGFloat(crossfadeAlpha),
            isRealVideoFrame: isRealVideoFrame
        )
    }

    return pixelBuffer
}

class FastVideoClipSampler {
    let asset: AVURLAsset
    let durationSec: Double
    var reader: AVAssetReader?
    var output: AVAssetReaderTrackOutput?
    var currentStartSec: Double = 0.0
    var lastBundle: VideoBundle?
    let ciContext = CIContext(options: [.useSoftwareRenderer: false])

    init?(path: String) {
        let url = URL(fileURLWithPath: path)
        guard FileManager.default.fileExists(atPath: path) else { return nil }
        self.asset = AVURLAsset(url: url)
        let dur = CMTimeGetSeconds(self.asset.duration)
        guard dur > 0.5, self.asset.tracks(withMediaType: .video).first != nil else { return nil }
        self.durationSec = dur
    }

    func seek(to startSec: Double) {
        reader?.cancelReading()
        reader = nil
        output = nil
        let safeStart = max(0.0, min(startSec, max(0.0, durationSec - 1.5)))
        currentStartSec = safeStart

        guard let track = asset.tracks(withMediaType: .video).first,
              let newReader = try? AVAssetReader(asset: asset) else { return }

        let startTime = CMTimeMakeWithSeconds(safeStart, preferredTimescale: 600)
        newReader.timeRange = CMTimeRange(start: startTime, duration: CMTimeMakeWithSeconds(durationSec - safeStart, preferredTimescale: 600))

        let attrs: [String: Any] = [
            kCVPixelBufferPixelFormatTypeKey as String: Int(kCVPixelFormatType_32BGRA)
        ]
        let trackOut = AVAssetReaderTrackOutput(track: track, outputSettings: attrs)
        trackOut.alwaysCopiesSampleData = false
        if newReader.canAdd(trackOut) {
            newReader.add(trackOut)
            if newReader.startReading() {
                self.reader = newReader
                self.output = trackOut
            }
        }
    }

    private func processSample(_ pb: CVPixelBuffer) -> VideoBundle? {
        let ciImg = CIImage(cvPixelBuffer: pb)
        let isLandscape = ciImg.extent.width > ciImg.extent.height * 1.05

        let sharpen = CIFilter(name: "CISharpenLuminance", parameters: [
            kCIInputImageKey: ciImg,
            kCIInputSharpnessKey: 0.70
        ])
        let sharpCI = sharpen?.outputImage ?? ciImg
        guard let sharpCG = ciContext.createCGImage(sharpCI, from: ciImg.extent) else { return lastBundle }

        var blurCG: CGImage? = nil
        if isLandscape {
            let blur = ciImg.clampedToExtent().applyingGaussianBlur(sigma: 40.0).cropped(to: ciImg.extent)
            blurCG = ciContext.createCGImage(blur, from: ciImg.extent)
        }
        let b = VideoBundle(sharp: sharpCG, blur: blurCG)
        lastBundle = b
        return b
    }

    func nextBundle() -> VideoBundle? {
        guard let out = output, let r = reader else { return lastBundle }
        if r.status == .reading, let sample = out.copyNextSampleBuffer(), let pb = CMSampleBufferGetImageBuffer(sample) {
            return processSample(pb)
        } else if r.status == .completed {
            seek(to: 1.0)
            if let out2 = output, let sample = out2.copyNextSampleBuffer(), let pb = CMSampleBufferGetImageBuffer(sample) {
                return processSample(pb)
            }
        }
        return lastBundle
    }
}

func renderVideo(manifestPath: String) throws {
    let data = try Data(contentsOf: URL(fileURLWithPath: manifestPath))
    let manifest = try JSONDecoder().decode(RenderManifest.self, from: data)

    let tempSilentURL = URL(fileURLWithPath: manifest.output_mp4_path + ".silent.mp4")
    let finalURL = URL(fileURLWithPath: manifest.output_mp4_path)

    try? FileManager.default.removeItem(at: tempSilentURL)
    try? FileManager.default.removeItem(at: finalURL)

    let width = 1080
    let height = 1920
    let fps: Int32 = 30

    let writer = try AVAssetWriter(outputURL: tempSilentURL, fileType: .mp4)
    let videoSettings: [String: Any] = [
        AVVideoCodecKey: AVVideoCodecType.h264,
        AVVideoWidthKey: width,
        AVVideoHeightKey: height,
        AVVideoCompressionPropertiesKey: [
            AVVideoAverageBitRateKey: 9_500_000,
            AVVideoProfileLevelKey: AVVideoProfileLevelH264HighAutoLevel
        ]
    ]
    let writerInput = AVAssetWriterInput(mediaType: .video, outputSettings: videoSettings)
    writerInput.expectsMediaDataInRealTime = false

    let sourceBufferAttributes: [String: Any] = [
        kCVPixelBufferPixelFormatTypeKey as String: Int(kCVPixelFormatType_32BGRA),
        kCVPixelBufferWidthKey as String: width,
        kCVPixelBufferHeightKey as String: height,
        kCVPixelBufferCGImageCompatibilityKey as String: true,
        kCVPixelBufferCGBitmapContextCompatibilityKey as String: true
    ]
    let adaptor = AVAssetWriterInputPixelBufferAdaptor(
        assetWriterInput: writerInput,
        sourcePixelBufferAttributes: sourceBufferAttributes
    )

    writer.add(writerInput)
    writer.startWriting()
    writer.startSession(atSourceTime: .zero)

    let images: [CGImage?] = manifest.scenes.map { loadCGImage(path: $0.image_path) }
    var samplersCache: [String: FastVideoClipSampler] = [:]
    for scene in manifest.scenes {
        if let vp = scene.video_path, !vp.isEmpty, samplersCache[vp] == nil {
            if let s = FastVideoClipSampler(path: vp) {
                samplersCache[vp] = s
            }
        }
    }

    var globalFrameIdx: Int64 = 0

    guard let pool = adaptor.pixelBufferPool else {
        throw NSError(domain: "VideoRenderer", code: 2)
    }

    let fadeFrames = 5

    for (sIdx, scene) in manifest.scenes.enumerated() {
        let sceneFrames = max(1, Int(round(scene.duration_sec * Double(fps))))
        let fallbackImg = images[sIdx]
        let nextFallbackImg: CGImage? = (sIdx + 1 < images.count) ? images[sIdx + 1] : nil
        let nextMotion: String = (sIdx + 1 < manifest.scenes.count) ? manifest.scenes[sIdx + 1].motion : "zoom_in"

        var activeSampler: FastVideoClipSampler? = nil
        if let vp = scene.video_path, let sampler = samplersCache[vp] {
            activeSampler = sampler
            // Jump to a distinct segment of the source video for each scene cut so it looks like multi-cut real review footage
            let defaultStart: Double
            if let explicitStart = scene.video_start_sec {
                defaultStart = explicitStart
            } else {
                let usableDur = max(4.0, sampler.durationSec - 4.0)
                let step = usableDur / Double(max(1, manifest.scenes.count))
                defaultStart = 1.5 + Double(sIdx) * step
            }
            sampler.seek(to: defaultStart)
        }

        for f in 0..<sceneFrames {
            while !writerInput.isReadyForMoreMediaData {
                Thread.sleep(forTimeInterval: 0.002)
            }
            let progress = Double(f) / Double(max(1, sceneFrames - 1))
            let globalTimeSec = Double(globalFrameIdx) / Double(fps)

            let bundle = activeSampler?.nextBundle()
            let currentImg = bundle?.sharp ?? fallbackImg
            let currentBlur = bundle?.blur
            let isRealVideo = (bundle != nil)

            var crossfadeAlpha = 0.0
            if !isRealVideo && nextFallbackImg != nil && f >= (sceneFrames - fadeFrames) {
                crossfadeAlpha = Double(f - (sceneFrames - fadeFrames)) / Double(fadeFrames)
            }

            if let pb = createCleanPixelBuffer(
                pool: pool,
                width: width,
                height: height,
                currentImage: currentImg,
                currentBlurImage: currentBlur,
                nextImage: nextFallbackImg,
                currentMotion: scene.motion,
                nextMotion: nextMotion,
                progress: progress,
                globalTimeSec: globalTimeSec,
                crossfadeAlpha: crossfadeAlpha,
                isRealVideoFrame: isRealVideo
            ) {
                let presentationTime = CMTimeMake(value: globalFrameIdx, timescale: fps)
                adaptor.append(pb, withPresentationTime: presentationTime)
            }
            globalFrameIdx += 1
        }
    }

    writerInput.markAsFinished()
    let writeSem = DispatchSemaphore(value: 0)
    writer.finishWriting { writeSem.signal() }
    writeSem.wait()

    let composition = AVMutableComposition()
    let videoAsset = AVURLAsset(url: tempSilentURL)

    if let videoTrack = videoAsset.tracks(withMediaType: .video).first,
       let compVideoTrack = composition.addMutableTrack(withMediaType: .video, preferredTrackID: kCMPersistentTrackID_Invalid) {
        try? compVideoTrack.insertTimeRange(
            CMTimeRange(start: .zero, duration: videoAsset.duration),
            of: videoTrack,
            at: .zero
        )
    }

    if let compAudioTrack = composition.addMutableTrack(withMediaType: .audio, preferredTrackID: kCMPersistentTrackID_Invalid) {
        var sceneStartSec: Double = 0.0
        var insertedAnySceneAudio = false

        for scene in manifest.scenes {
            if let ap = scene.audio_path, FileManager.default.fileExists(atPath: ap) {
                let aAsset = AVURLAsset(url: URL(fileURLWithPath: ap))
                if let aTrack = aAsset.tracks(withMediaType: .audio).first {
                    let insertTime = CMTimeMakeWithSeconds(sceneStartSec, preferredTimescale: 600)
                    let maxDur = CMTimeMakeWithSeconds(scene.duration_sec, preferredTimescale: 600)
                    let actualDur = CMTimeMinimum(aAsset.duration, maxDur)
                    try? compAudioTrack.insertTimeRange(
                        CMTimeRange(start: .zero, duration: actualDur),
                        of: aTrack,
                        at: insertTime
                    )
                    insertedAnySceneAudio = true
                }
            }
            sceneStartSec += scene.duration_sec
        }

        if !insertedAnySceneAudio && FileManager.default.fileExists(atPath: manifest.audio_path) {
            let audioAsset = AVURLAsset(url: URL(fileURLWithPath: manifest.audio_path))
            if let audioTrack = audioAsset.tracks(withMediaType: .audio).first {
                let dur = CMTimeMinimum(videoAsset.duration, audioAsset.duration)
                try? compAudioTrack.insertTimeRange(
                    CMTimeRange(start: .zero, duration: dur),
                    of: audioTrack,
                    at: .zero
                )
            }
        }
    }

    if let exportSession = AVAssetExportSession(asset: composition, presetName: AVAssetExportPresetHighestQuality) {
        exportSession.outputURL = finalURL
        exportSession.outputFileType = .mp4
        exportSession.shouldOptimizeForNetworkUse = true
        let exportSem = DispatchSemaphore(value: 0)
        exportSession.exportAsynchronously { exportSem.signal() }
        exportSem.wait()
        try? FileManager.default.removeItem(at: tempSilentURL)
        return
    }

    try FileManager.default.moveItem(at: tempSilentURL, to: finalURL)
}

if CommandLine.arguments.count < 2 {
    fputs("Usage: video_renderer <manifest.json>\n", stderr)
    exit(1)
}

do {
    try renderVideo(manifestPath: CommandLine.arguments[1])
    print("RENDER_MP4_OK")
} catch {
    fputs("Render error: \(error)\n", stderr)
    exit(2)
}
