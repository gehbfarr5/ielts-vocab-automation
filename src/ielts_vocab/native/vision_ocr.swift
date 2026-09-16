import Foundation
import Vision
import ImageIO

// Local text recognition; no image leaves the Mac.
struct Line: Codable { let text: String; let confidence: Float; let bbox: [Double] }
do {
    guard CommandLine.arguments.count == 2 else {
        throw NSError(domain: "Usage: vision-ocr image.png", code: 1)
    }
    let url = URL(fileURLWithPath: CommandLine.arguments[1])
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.recognitionLanguages = ["en-US"]
    request.usesLanguageCorrection = false
    try VNImageRequestHandler(url: url).perform([request])
    let lines = (request.results ?? []).compactMap { item -> Line? in
        guard let text = item.topCandidates(1).first else { return nil }
        let b = item.boundingBox
        return Line(text: text.string, confidence: text.confidence,
                    bbox: [b.minX, 1 - b.maxY, b.width, b.height])
    }
    FileHandle.standardOutput.write(try JSONEncoder().encode(lines))
} catch {
    FileHandle.standardError.write(Data("OCR failed: \(error)\n".utf8))
    exit(1)
}
