#!/usr/bin/env swift
/**
 * Apple Vision OCR：识别图片中的文字。
 *
 * 用法：
 *   swift ocr_vision.swift <image_path>
 *   cat image.png | swift ocr_vision.swift -
 *
 * 输出：识别到的文字（按位置从上到下排列），stdout 输出。
 * 退出码：0=成功, 1=参数错误, 2=识别失败
 */

import Foundation
import Vision
import AppKit

func recognizeText(from image: NSImage) -> [String] {
    guard let cgImage = image.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
        fputs("错误：无法转换图片格式\n", stderr)
        exit(2)
    }

    var results: [String] = []
    let semaphore = DispatchSemaphore(value: 0)

    let request = VNRecognizeTextRequest { request, error in
        defer { semaphore.signal() }

        if let error = error {
            fputs("识别错误：\(error.localizedDescription)\n", stderr)
            return
        }

        guard let observations = request.results as? [VNRecognizedTextObservation] else {
            return
        }

        // 按 y 坐标从上到下排序（Vision 坐标系 y 轴朝上，所以反转）
        let sorted = observations.sorted { $0.boundingBox.origin.y > $1.boundingBox.origin.y }

        for observation in sorted {
            if let candidate = observation.topCandidates(1).first {
                results.append(candidate.string)
            }
        }
    }

    request.recognitionLevel = .accurate
    request.recognitionLanguages = ["zh-Hans", "zh-Hant", "en"]
    request.usesLanguageCorrection = true

    let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
    do {
        try handler.perform([request])
    } catch {
        fputs("执行识别失败：\(error.localizedDescription)\n", stderr)
        exit(2)
    }

    semaphore.wait()
    return results
}

// --- main ---

guard CommandLine.arguments.count >= 2 else {
    fputs("用法：swift ocr_vision.swift <image_path | ->\n", stderr)
    exit(1)
}

let arg = CommandLine.arguments[1]
let image: NSImage

if arg == "-" {
    // 从 stdin 读取
    let data = FileHandle.standardInput.readDataToEndOfFile()
    guard let img = NSImage(data: data) else {
        fputs("错误：无法从 stdin 读取图片\n", stderr)
        exit(2)
    }
    image = img
} else {
    // 从文件读取
    let url = URL(fileURLWithPath: arg)
    guard let img = NSImage(contentsOf: url) else {
        fputs("错误：无法读取图片文件 \(arg)\n", stderr)
        exit(2)
    }
    image = img
}

let lines = recognizeText(from: image)

if lines.isEmpty {
    fputs("未识别到文字\n", stderr)
    exit(0)
}

print(lines.joined(separator: "\n"))
