// Cut each portrait's person out of its background and find the face, with Apple Vision.
// swift cutout.swift <portrait dir> <out dir>
// Writes <out>/<name>.png (the person on transparent) and <out>/faces.json
// (face box per file, top-left origin, fractions of the image).
import AppKit
import CoreImage
import Foundation
import Vision

let args = CommandLine.arguments
guard args.count == 3 else { print("usage: cutout.swift <in> <out>"); exit(1) }
let inDir = URL(fileURLWithPath: args[1]), outDir = URL(fileURLWithPath: args[2])
try? FileManager.default.createDirectory(at: outDir, withIntermediateDirectories: true)
let ctx = CIContext()
var report: [[String: Any]] = []

let names = try FileManager.default.contentsOfDirectory(atPath: inDir.path)
    .filter { $0.hasSuffix(".jpg") && $0 != "ground.jpg" }.sorted()
for name in names {
    let url = inDir.appendingPathComponent(name)
    guard let image = CIImage(contentsOf: url) else { continue }
    let handler = VNImageRequestHandler(ciImage: image, options: [:])
    let faceReq = VNDetectFaceRectanglesRequest()
    let maskReq = VNGenerateForegroundInstanceMaskRequest()
    do { try handler.perform([faceReq, maskReq]) } catch { print(name, "vision failed:", error); continue }

    var entry: [String: Any] = ["file": name, "w": image.extent.width, "h": image.extent.height]
    let faces = (faceReq.results ?? []).sorted { $0.boundingBox.width > $1.boundingBox.width }
    if let f = faces.first?.boundingBox {
        entry["face"] = [f.minX, 1 - f.maxY, f.width, f.height]
    }
    if let obs = maskReq.results?.first {
        // keep only the instance under the face, so flags and chairs drop out
        var keep = obs.allInstances
        if let f = faces.first?.boundingBox {
            let buf = obs.instanceMask
            CVPixelBufferLockBaseAddress(buf, .readOnly)
            let w = CVPixelBufferGetWidth(buf), h = CVPixelBufferGetHeight(buf)
            let row = CVPixelBufferGetBytesPerRow(buf)
            let base = CVPixelBufferGetBaseAddress(buf)!.assumingMemoryBound(to: UInt8.self)
            let x = min(w - 1, Int(f.midX * CGFloat(w))), y = min(h - 1, Int((1 - f.midY) * CGFloat(h)))
            let label = base[y * row + x]
            CVPixelBufferUnlockBaseAddress(buf, .readOnly)
            if label != 0 { keep = IndexSet(integer: Int(label)) }
            entry["instances"] = obs.allInstances.count
        }
        do {
            let masked = try obs.generateMaskedImage(ofInstances: keep, from: handler, croppedToInstancesExtent: false)
            let out = outDir.appendingPathComponent(name.replacingOccurrences(of: ".jpg", with: ".png"))
            try ctx.writePNGRepresentation(of: CIImage(cvPixelBuffer: masked), to: out, format: .RGBA8,
                                           colorSpace: CGColorSpace(name: CGColorSpace.sRGB)!)
            entry["cut"] = true
        } catch { print(name, "mask failed:", error) }
    }
    report.append(entry)
    print(name, entry["face"] != nil ? "face" : "NO FACE", entry["cut"] != nil ? "cut" : "NO CUT")
}
let data = try JSONSerialization.data(withJSONObject: report, options: [.prettyPrinted, .sortedKeys])
try data.write(to: outDir.appendingPathComponent("faces.json"))
