import Foundation
import AVFoundation
import Vision
import AppKit

// Công cụ kiểm tra video review thực tế sử dụng Apple Vision Framework:
// - Phát hiện khuôn mặt lớn (talking head / vlogger quay cả người / đứng nói chuyện trước ống kính)
// - Phát hiện bàn tay thao tác trên sản phẩm (hands-on)
// Trả về JSON: {"is_hands_on": true/false, "faces_detected": n, "hands_detected": m, "score": x}

let args = CommandLine.arguments
guard args.count >= 2 else {
    print("{\"ok\": false, \"error\": \"Missing video path argument\"}")
    exit(1)
}

let videoPath = args[1]
let url = URL(fileURLWithPath: videoPath)
guard FileManager.default.fileExists(atPath: videoPath) else {
    print("{\"ok\": false, \"error\": \"File not found\"}")
    exit(1)
}

let asset = AVURLAsset(url: url)
let dur = CMTimeGetSeconds(asset.duration)
guard dur >= 2.0 else {
    print("{\"ok\": false, \"error\": \"Duration too short\"}")
    exit(1)
}

let generator = AVAssetImageGenerator(asset: asset)
generator.appliesPreferredTrackTransform = true
generator.requestedTimeToleranceBefore = .zero
generator.requestedTimeToleranceAfter = .zero

// Kiểm tra 5 điểm thời gian trong video
let samplePoints = [dur * 0.15, dur * 0.35, dur * 0.55, dur * 0.75, dur * 0.90]
var faceFramesCount = 0
var maxFaceArea: CGFloat = 0.0
var totalHandsCount = 0

for tSec in samplePoints {
    let cmTime = CMTime(seconds: tSec, preferredTimescale: 600)
    guard let cgImg = try? generator.copyCGImage(at: cmTime, actualTime: nil) else {
        continue
    }

    // 1. Quét khuôn mặt
    let faceReq = VNDetectFaceRectanglesRequest()
    let faceHandler = VNImageRequestHandler(cgImage: cgImg, options: [:])
    try? faceHandler.perform([faceReq])
    let faces = faceReq.results ?? []
    
    var frameHasFace = false
    for face in faces {
        let area = face.boundingBox.width * face.boundingBox.height
        if area > 0.010 { // Khuôn mặt chiếm > 1% diện tích màn hình
            frameHasFace = true
            if area > maxFaceArea { maxFaceArea = area }
        }
    }
    if frameHasFace {
        faceFramesCount += 1
    }

    // 2. Quét bàn tay người thao tác
    let handReq = VNDetectHumanHandPoseRequest()
    handReq.maximumHandCount = 3
    let handHandler = VNImageRequestHandler(cgImage: cgImg, options: [:])
    try? handHandler.perform([handReq])
    let hands = handReq.results ?? []
    totalHandsCount += hands.count
}

// Tiêu chí chấp nhận video chuẩn Review Thực Tế 100% Đôi Tay:
// 1. Tuyệt đối không xuất hiện khuôn mặt vlogger/người nói chuyện (faceFramesCount == 0)
// 2. Bắt buộc có bàn tay người thực thao tác trên sản phẩm (totalHandsCount >= 1) -> Loại bỏ hoàn toàn đồ họa 3D CGI / banner quảng cáo
let isHandsOn = (faceFramesCount == 0) && (totalHandsCount >= 1)

print("{\"ok\": true, \"video\": \"\(videoPath)\", \"is_hands_on\": \(isHandsOn), \"face_frames\": \(faceFramesCount), \"sample_count\": \(samplePoints.count), \"max_face_area\": \(maxFaceArea), \"hands_detected\": \(totalHandsCount)}")
exit(isHandsOn ? 0 : 2)
