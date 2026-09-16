import Foundation
import Vision
import ImageIO

// Local text recognition; no image leaves the Mac.
struct Word: Codable { let text: String; let bbox: [Double] }
struct Line: Codable { let text: String; let confidence: Float; let bbox: [Double]; let words: [Word] }
func normalized(_ b: CGRect) -> [Double] { [b.minX, 1 - b.maxY, b.width, b.height] }
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
    let lines = try (request.results ?? []).compactMap { item -> Line? in
        guard let text = item.topCandidates(1).first else { return nil }
        let string = text.string
        let regex = try NSRegularExpression(pattern: "\\S+")
        let matches = regex.matches(in: string, range: NSRange(string.startIndex..., in: string))
        let words = try matches.map { match -> Word in
            guard let range = Range(match.range, in: string),
                  let box = try text.boundingBox(for: range) else {
                throw NSError(domain: "Vision word bounding box unavailable", code: 2)
            }
            return Word(text: String(string[range]), bbox: normalized(box.boundingBox))
        }
        return Line(text: string, confidence: text.confidence,
                    bbox: normalized(item.boundingBox), words: words)
    }
    FileHandle.standardOutput.write(try JSONEncoder().encode(lines))
} catch {
    FileHandle.standardError.write(Data("OCR failed: \(error)\n".utf8))
    exit(1)
}
