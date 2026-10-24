package com.bittle.orchestrator.adapter.in.web;

import com.bittle.orchestrator.application.usecase.GetRobotIntroductionUseCase;
import com.bittle.orchestrator.application.usecase.SetRobotIntroductionUseCase;
import com.bittle.orchestrator.domain.robot.RobotIntroduction;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@Tag(name = "Introduction", description = "What she says to \"Hey Laika, introduce yourself\" — "
        + "owned here, pushed to the adapter like the operating mode")
@RequestMapping("/api/robots/{robotId}/conversation/introduction")
public class IntroductionController {

    private final GetRobotIntroductionUseCase getIntroduction;
    private final SetRobotIntroductionUseCase setIntroduction;

    public IntroductionController(GetRobotIntroductionUseCase getIntroduction,
                                  SetRobotIntroductionUseCase setIntroduction) {
        this.getIntroduction = getIntroduction;
        this.setIntroduction = setIntroduction;
    }

    @Operation(summary = "The stored self-introduction",
            description = "Empty text means nothing has been written yet and the adapter is "
                    + "still speaking its compiled default.")
    @GetMapping
    public RobotIntroduction introduction(@PathVariable String robotId) {
        return getIntroduction.execute(robotId);
    }

    @Operation(summary = "Store the self-introduction and push it to the robot",
            description = "Body: {\"introduction\": \"...\"}. Persisted first, then pushed to "
                    + "the adapter best-effort; the boot resync re-pushes to a robot that was "
                    + "offline. At most 2000 characters, and note the adapter trims the spoken "
                    + "reply at CONVERSATION_REPLY_CHARS.")
    @PostMapping
    public RobotIntroduction set(@PathVariable String robotId,
                                 @RequestBody Map<String, String> body,
                                 @RequestParam(defaultValue = "gui") String via) {
        return setIntroduction.execute(robotId, body == null ? null : body.get("introduction"), via);
    }
}
